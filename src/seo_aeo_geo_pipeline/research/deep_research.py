"""Deep Research Agent - real LLM-powered research using litellm.

Consumes:
  - Selected opportunity from Discovery
  - Dify retrieved knowledge (when configured)
  - SE Ranking signals from Discovery
  - Web/search research via LLM

Produces:
  - Structured ResearchDataset with verified facts, sources, content gaps

Does NOT generate final HTML. Does NOT use Dify as orchestrator.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from seo_aeo_geo_pipeline.research import normalize_source, create_research_snapshot
from seo_aeo_geo_pipeline.research.agents.research_agent import (
    ResearchDataset,
    ResearchPlan,
    SubQuestion,
)
from seo_aeo_geo_pipeline.research.dify_rag import DifyRAGClient, KnowledgeRetrieval
from seo_aeo_geo_pipeline.observability.llm_trace import record_llm_call

logger = logging.getLogger(__name__)


def _call_llm(
    prompt: str,
    model: str = "openrouter/inclusionai/ling-3.0-flash-sante",
    max_tokens: int = 4096,
    operation: str = "research_llm",
) -> str:
    """Call LLM via litellm. Returns response text or raises.

    Raises:
        RuntimeError with clear message for rate-limit, auth, or other failures.
    """
    import time as _time
    start = _time.monotonic()
    try:
        import litellm
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        latency = (_time.monotonic() - start) * 1000
        record_llm_call(
            operation=operation,
            model=model,
            stage="research",
            success=True,
            response=response,
            latency_ms=latency,
        )
        return response.choices[0].message.content or ""
    except ImportError:
        raise RuntimeError("litellm not installed. Run: pip install 'seo-aeo-geo-pipeline[llm]'")
    except Exception as e:
        latency = (_time.monotonic() - start) * 1000
        err_msg = str(e).lower()
        is_rate_limit = ("rate" in err_msg and ("limit" in err_msg or "429" in err_msg)) or \
                        "ratelimit" in err_msg.replace(" ", "") or "rate_limit" in err_msg
        record_llm_call(
            operation=operation,
            model=model,
            stage="research",
            success=False,
            error=e,
            latency_ms=latency,
            metadata={"rate_limit": is_rate_limit},
        )
        # Detect rate-limit errors (OpenRouter 429 or litellm RateLimitError)
        if is_rate_limit:
            raise RuntimeError(f"RATE_LIMIT: OpenRouter free-model daily quota exhausted. Retry after reset.")
        raise RuntimeError(f"LLM call failed: {e}")


def _parse_json_from_llm(text: str) -> dict:
    """Extract JSON object from LLM response text."""
    # Try direct parse
    text = text.strip()
    if text.startswith("```"):
        # Strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON block in text
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


class DeepResearchAgent:
    """LLM-powered deep research agent.

    Uses litellm for LLM calls. Optionally retrieves from Dify knowledge base.
    Produces structured ResearchDataset from opportunity keyword + intent.
    """

    def __init__(
        self,
        model: str = "openrouter/inclusionai/ling-3.0-flash-sante",
        dify_client: Optional[DifyRAGClient] = None,
        max_tokens: int = 4096,
        competitor_intel: Optional[Any] = None,
    ):
        self.model = model
        self.dify = dify_client or DifyRAGClient()
        self.max_tokens = max_tokens
        self.competitor_intel = competitor_intel  # Optional CompetitorIntel instance

    def plan_research(self, keyword: str, intent: str = "informational") -> ResearchPlan:
        """Create research plan with LLM-generated sub-questions."""
        prompt = f"""You are an SEO research planner. Given a target keyword and search intent,
generate a research plan with 3-5 specific sub-questions to investigate.

Keyword: "{keyword}"
Intent: {intent}

Return a JSON object with this exact structure:
{{
  "sub_questions": [
    {{"question": "...", "source_types": ["type1", "type2"]}}
  ],
  "target_audience": "description of the audience",
  "content_gaps": ["gap1", "gap2"],
  "competing_pages": ["page description 1", "page description 2"]
}}

Only return the JSON, no other text."""

        try:
            response = _call_llm(prompt, model=self.model, max_tokens=self.max_tokens)
            data = _parse_json_from_llm(response)
        except RuntimeError as e:
            logger.warning(f"LLM planning failed, using fallback: {e}")
            data = {}

        sub_questions = []
        for i, sq in enumerate(data.get("sub_questions", [])):
            sub_questions.append(SubQuestion(
                id=f"sq_{i+1}",
                question=sq.get("question", ""),
                intent=intent,
                source_types=sq.get("source_types", ["general_web"]),
            ))

        if not sub_questions:
            # Fallback template questions
            sub_questions = [
                SubQuestion(id="sq_1", question=f"What is {keyword} and how does it work?", intent=intent, source_types=["encyclopedic"]),
                SubQuestion(id="sq_2", question=f"What are the best {keyword} options?", intent=intent, source_types=["comparison"]),
                SubQuestion(id="sq_3", question=f"What problems does {keyword} solve?", intent=intent, source_types=["general_web"]),
            ]

        return ResearchPlan(
            primary_keyword=keyword,
            intent=intent,
            sub_questions=sub_questions,
            target_audience=data.get("target_audience", self._derive_audience(keyword, intent)),
            content_gaps=data.get("content_gaps", []),
            competing_pages=data.get("competing_pages", []),
        )

    def investigate(self, plan: ResearchPlan) -> ResearchDataset:
        """Investigate each sub-question using LLM + optional Dify knowledge + competitor intel."""
        all_sources = []
        evidence_by_claim = {}
        questions_answered = []

        # Step 1: Retrieve from Dify if configured
        dify_knowledge = None
        if self.dify.is_configured:
            dify_knowledge = self.dify.retrieve(plan.primary_keyword, top_k=5)
            if dify_knowledge.results:
                logger.info(f"Dify returned {len(dify_knowledge.results)} knowledge results")
                for r in dify_knowledge.results:
                    all_sources.append(normalize_source(
                        source_url=r.source_url or f"dify://knowledge",
                        source_type="dify_knowledge",
                        excerpt=r.content[:500],
                        confidence=r.score,
                        collector="dify_rag",
                        metadata=r.metadata,
                    ))

        # Step 1b: Build competitor research pack if configured
        competitor_pack = None
        if self.competitor_intel is not None:
            try:
                competitor_pack = self.competitor_intel.build_research_pack(
                    plan.primary_keyword, top_k=8
                )
                if competitor_pack.evidence:
                    logger.info(
                        f"Competitor intel: {len(competitor_pack.evidence)} evidence items "
                        f"from {len({e.competitor for e in competitor_pack.evidence})} competitors"
                    )
                    for e in competitor_pack.evidence:
                        all_sources.append(normalize_source(
                            source_url=e.url,
                            source_type="competitor_intelligence",
                            excerpt=e.relevant_content[:500],
                            confidence=e.relevance_score,
                            collector="competitor_crawler",
                            metadata={
                                "competitor": e.competitor,
                                "page_type": e.page_type,
                            },
                        ))
            except Exception as e:
                logger.warning(f"Competitor intel failed: {e}")

        # Step 2: Investigate each sub-question with LLM
        rate_limited = False
        non_rate_limit_errors = 0
        for sq in plan.sub_questions:
            try:
                evidence = self._investigate_question(sq, plan, dify_knowledge, competitor_pack)
                if evidence:
                    sq.answered = True
                    sq.evidence = evidence
                    evidence_by_claim[sq.question] = [evidence]
                    questions_answered.append(sq.question)
                    all_sources.append(normalize_source(
                        source_url=f"llm://{self.model}",
                        source_type="llm_research",
                        excerpt=evidence[:500],
                        confidence=0.7,
                        collector="deep_research_agent",
                        metadata={"question_id": sq.id, "model": self.model},
                    ))
            except RuntimeError as e:
                err_msg = str(e)
                if "RATE_LIMIT" in err_msg:
                    rate_limited = True
                    logger.warning(f"Rate-limited on '{sq.question}': {err_msg}")
                else:
                    non_rate_limit_errors += 1
                    logger.warning(f"Failed to investigate '{sq.question}': {e}")
            except Exception as e:
                non_rate_limit_errors += 1
                logger.warning(f"Failed to investigate '{sq.question}': {e}")

        if rate_limited:
            logger.warning(
                f"OpenRouter rate limit hit during investigation. "
                f"Answered {len(questions_answered)}/{len(plan.sub_questions)} questions. "
                f"Competitor intelligence and Dify knowledge are still available."
            )

        # Determine completion status with evidence quality checks
        min_questions_required = max(2, len(plan.sub_questions) // 2)  # At least half or 2, whichever is greater
        min_sources_required = max(2, min_questions_required)  # At least 2 sources

        has_sufficient_questions = len(questions_answered) >= min_questions_required
        has_sufficient_sources = len(all_sources) >= min_sources_required

        if rate_limited:
            completion_status = "partial_rate_limited"
        elif non_rate_limit_errors > 0 and len(questions_answered) < len(plan.sub_questions):
            completion_status = "partial_error"
        elif not has_sufficient_questions:
            completion_status = "partial_insufficient_questions"
        elif not has_sufficient_sources:
            completion_status = "partial_insufficient_sources"
        else:
            completion_status = "complete"

        # Content gaps = unanswered questions
        content_gaps = [sq.question for sq in plan.sub_questions if not sq.answered]

        # Page type recommendation
        page_type = self._recommend_page_type(plan)

        # AEO/GEO requirements
        aeo_geo_reqs = self._derive_aeo_geo_requirements(plan)

        # Differentiation
        differentiation = self._derive_differentiation(plan)

        return ResearchDataset(
            primary_keyword=plan.primary_keyword,
            intent=plan.intent,
            sources=all_sources,
            evidence_by_claim=evidence_by_claim,
            content_gaps=content_gaps,
            competing_analysis=[{"page": p} for p in plan.competing_pages],
            questions_answered=questions_answered,
            audience_profile=plan.target_audience,
            schema_markup_needs=aeo_geo_reqs,
            aeo_geo_requirements=aeo_geo_reqs,
            differentiation_strategy=differentiation,
            page_type_recommendation=page_type,
            completion_status=completion_status,
        )

    def _investigate_question(
        self,
        sq: SubQuestion,
        plan: ResearchPlan,
        dify_knowledge: Optional[KnowledgeRetrieval] = None,
        competitor_pack=None,
    ) -> str:
        """Investigate a single sub-question using LLM."""
        # Build context from Dify knowledge
        context_parts = []
        if dify_knowledge and dify_knowledge.results:
            for r in dify_knowledge.results[:3]:
                context_parts.append(f"Knowledge: {r.content[:300]}")

        # Add competitor intelligence context
        if competitor_pack and competitor_pack.evidence:
            for e in competitor_pack.evidence[:3]:
                context_parts.append(f"Competitor ({e.competitor}): {e.relevant_content[:300]}")

        context_str = "\n".join(context_parts) if context_parts else "No prior knowledge available."

        prompt = f"""Research the following question about "{plan.primary_keyword}" (intent: {plan.intent}).

Question: {sq.question}

Available context:
{context_str}

Provide a concise, factual answer (2-4 sentences). Focus on:
- Key facts and data points
- Specific tools, platforms, or methods mentioned
- Practical insights a content creator would need

Return only the answer text, no JSON or formatting."""

        response = _call_llm(prompt, model=self.model, max_tokens=1024)
        return response.strip()

    def _derive_audience(self, keyword: str, intent: str) -> str:
        audience_map = {
            "commercial": "Buyers evaluating advertising/automation tools and platforms",
            "transactional": "Implementers ready to adopt or integrate advertising solutions",
            "informational": "Researchers learning about advertising technology and strategies",
        }
        return audience_map.get(intent, "Digital advertisers and marketing professionals")

    def _recommend_page_type(self, plan: ResearchPlan) -> str:
        mapping = {
            "commercial": "comparison-guide",
            "transactional": "product-how-to",
            "informational": "role-guide",
        }
        return mapping.get(plan.intent, "comparison-guide")

    def _derive_differentiation(self, plan: ResearchPlan) -> str:
        if plan.intent == "commercial":
            return "Compare across key evaluation criteria: price, features, usability, integration ecosystem"
        elif plan.intent == "transactional":
            return "Detail implementation pathway: prerequisites, configuration, expected outcomes, ROI"
        else:
            return "Establish topical expertise through comprehensive coverage, data points, and expert citations"

    def _derive_aeo_geo_requirements(self, plan: ResearchPlan) -> list[str]:
        if plan.intent == "commercial":
            return [
                "Include comparison table with schema.org Table markup",
                "Add FAQ schema for buyer questions",
                "Structure product signals with JSON-LD",
            ]
        elif plan.intent == "transactional":
            return [
                "Include how-to schema markup",
                "Add product specification structured data",
                "Structure implementation steps with schema.org",
            ]
        else:
            return [
                "Include FAQ schema markup",
                "Use semantic HTML headings (h1, h2, h3)",
                "Add internal links to related entities",
            ]

    def to_research_snapshot(self, dataset: ResearchDataset, opportunity_id: int = 1) -> dict:
        """Convert ResearchDataset to normalized snapshot."""
        snapshot = create_research_snapshot(
            opportunity_id=opportunity_id,
            sources=dataset.sources,
            data_hash=self._compute_data_hash(dataset),
            provider="deep_research_agent",
        )
        return {
            **snapshot,
            "primary_keyword": dataset.primary_keyword,
            "intent": dataset.intent,
            "content_gaps": dataset.content_gaps,
            "differentiation_strategy": dataset.differentiation_strategy,
            "page_type_recommendation": dataset.page_type_recommendation,
            "aeo_geo_requirements": dataset.aeo_geo_requirements,
            "schema_markup_needs": dataset.schema_markup_needs,
            "competing_analysis": dataset.competing_analysis,
            "questions_answered": dataset.questions_answered,
            "audience_profile": dataset.audience_profile,
            "completion_status": dataset.completion_status,
        }

    def _compute_data_hash(self, dataset: ResearchDataset) -> str:
        parts = [dataset.primary_keyword, dataset.intent, str(len(dataset.sources)), str(len(dataset.content_gaps))]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def run_full_cycle(
        self,
        keyword: str,
        intent: str = "informational",
        opportunity_id: int = 1,
        competitor_pages: Optional[list[str]] = None,
    ) -> dict:
        """Full research cycle: plan -> investigate -> snapshot.

        Returns dict with keys: plan, dataset, snapshot
        """
        plan = self.plan_research(keyword, intent)
        if competitor_pages:
            plan.competing_pages = competitor_pages

        dataset = self.investigate(plan)
        snapshot = self.to_research_snapshot(dataset, opportunity_id)

        return {
            "plan": plan,
            "dataset": dataset,
            "snapshot": snapshot,
        }
