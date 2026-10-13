"""Minimum Viable Deep Research Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from seo_aeo_geo_pipeline.research import normalize_source, create_research_snapshot


@dataclass
class SubQuestion:
    """A sub-question to investigate during research."""
    id: str
    question: str
    intent: str
    source_types: List[str] = field(default_factory=list)
    answered: bool = False
    evidence: Optional[str] = None


@dataclass
class ResearchPlan:
    """A research plan derived from the opportunity keyword."""
    primary_keyword: str
    intent: str
    sub_questions: List[SubQuestion] = field(default_factory=list)
    target_audience: str = ""
    content_gaps: List[str] = field(default_factory=list)
    competing_pages: List[str] = field(default_factory=list)


@dataclass
class ResearchDataset:
    """Structured research output matching the normalized research schema."""
    primary_keyword: str
    intent: str
    sources: List[dict] = field(default_factory=list)
    evidence_by_claim: Dict[str, List[str]] = field(default_factory=dict)
    content_gaps: List[str] = field(default_factory=list)
    competing_analysis: List[dict] = field(default_factory=list)
    questions_answered: List[str] = field(default_factory=list)
    audience_profile: str = ""
    schema_markup_needs: List[str] = field(default_factory=list)
    aeo_geo_requirements: List[str] = field(default_factory=list)
    differentiation_strategy: str = ""
    page_type_recommendation: str = ""
    completion_status: str = "complete"  # "complete" | "partial_rate_limited" | "partial_error"


class ResearchAgent:
    """Minimum viable deep research agent."""

    def __init__(self, use_mcp: bool = False, mcp_config: Optional[dict] = None) -> None:
        self.use_mcp = use_mcp
        self.mcp_config = mcp_config or {}

    def plan_research(self, keyword: str, intent: str = "informational") -> ResearchPlan:
        if intent == "commercial":
            gap_strategies = ["comparison frameworks", "feature tables", "price/value analysis"]
        elif intent == "transactional":
            gap_strategies = ["buy-box analysis", "implementation requirements", "ROI calculators"]
        else:
            gap_strategies = ["frequently asked questions", "expert perspectives", "step-by-step guides"]

        sub_questions = self._generate_sub_questions(keyword, intent, gap_strategies)
        audience = self._derive_audience(keyword, intent)
        competitors = self._derive_competitors(keyword, intent)

        return ResearchPlan(
            primary_keyword=keyword,
            intent=intent,
            sub_questions=sub_questions,
            target_audience=audience,
            content_gaps=[],
            competing_pages=competitors,
        )

    def _generate_sub_questions(self, keyword: str, intent: str, gap_strategies: List[str]) -> List[SubQuestion]:
        base_questions = {
            "informational": [
                f"What is {keyword} and how does it work?",
                f"What are the key benefits of {keyword}?",
                f"What problems does {keyword} solve?",
            ],
            "commercial": [
                f"What are the best {keyword} options on the market?",
                f"How do the top {keyword} compare on price and features?",
                f"What should I look for when buying {keyword}?",
            ],
            "transactional": [
                f"What do I need to implement {keyword}?",
                f"What are the system requirements for {keyword}?",
                f"How do I measure success with {keyword}?",
            ],
        }
        intent_questions = base_questions.get(intent, base_questions["informational"])

        sub_questions = []
        for i, q in enumerate(intent_questions):
            sub_questions.append(SubQuestion(
                id=f"sq_{i+1}",
                question=q,
                intent=intent,
                source_types=self._guess_source_types(q),
            ))

        return sub_questions

    def _guess_source_types(self, question: str) -> List[str]:
        question_lower = question.lower()
        sources = []
        if "compare" in question_lower or "vs" in question_lower:
            sources.append("serp_comparison")
        if "how" in question_lower or "step" in question_lower:
            sources.append("tutorial_guides")
        if "what is" in question_lower or "definition" in question_lower:
            sources.append("encyclopedic_references")
        if "price" in question_lower or "cost" in question_lower:
            sources.append("pricing_data")
        if not sources:
            sources.append("general_web")
        return sources

    def _derive_audience(self, keyword: str, intent: str) -> str:
        audience_map = {
            "informational": "researchers and learners",
            "commercial": "buyers evaluating options",
            "transactional": "implementers and decision-makers",
        }
        return audience_map.get(intent, "general audience")

    def _derive_competitors(self, keyword: str, intent: str) -> List[str]:
        """Derive competitor pages from keyword context.

        Returns empty list by default. Competitors should come from
        the SE Ranking discovery layer, not hardcoded fallbacks.
        """
        return []

    def investigate(self, plan: ResearchPlan) -> ResearchDataset:
        sources = []
        evidence_by_claim = {}
        content_gaps = []
        questions_answered = []
        competing_analysis = plan.competing_pages

        for sq in plan.sub_questions:
            if sq.answered and sq.evidence:
                evidence_by_claim[sq.question] = [sq.evidence]
                questions_answered.append(sq.question)
                source = normalize_source(
                    source_url=f"fixture://{sq.id}",
                    source_type=sq.source_types[0] if sq.source_types else "fixture",
                    excerpt=sq.evidence or "",
                    confidence=0.8,
                    collector="research_agent",
                    metadata={"question_id": sq.id},
                )
                sources.append(source)

        answered_ids = {sq.id for sq in plan.sub_questions if sq.answered and sq.evidence}
        for sq in plan.sub_questions:
            if sq.id not in answered_ids:
                content_gaps.append(sq.question)

        page_type = self._recommend_page_type(plan)

        if plan.intent == "commercial":
            aeo_geo_reqs = [
                "Include comparison table with schema.org Table markup",
                "Add FAQ schema for buyer questions",
                "Structure product signals with JSON-LD",
            ]
        elif plan.intent == "transactional":
            aeo_geo_reqs = [
                "Include how-to schema markup",
                "Add product specification structured data",
                "Structure implementation steps with schema.org",
            ]
        else:
            aeo_geo_reqs = [
                "Include FAQ schema markup",
                "Use semantic HTML headings (h1, h2, h3)",
                "Add internal links to related entities",
            ]

        return ResearchDataset(
            primary_keyword=plan.primary_keyword,
            intent=plan.intent,
            sources=sources,
            evidence_by_claim=evidence_by_claim,
            content_gaps=content_gaps,
            competing_analysis=competing_analysis,
            questions_answered=questions_answered,
            audience_profile=plan.target_audience,
            schema_markup_needs=aeo_geo_reqs,
            differentiation_strategy=self._derive_differentiation(plan),
            page_type_recommendation=page_type,
        )

    def _derive_differentiation(self, plan: ResearchPlan) -> str:
        if plan.intent == "commercial":
            return "Compare across key evaluation criteria: price, features, usability, integration"
        elif plan.intent == "transactional":
            return "Detail implementation pathway: prerequisites, configuration, expected outcomes"
        else:
            return "Establish topical expertise through comprehensive coverage and expert citations"

    def _recommend_page_type(self, plan: ResearchPlan) -> str:
        mapping = {
            "commercial": "comparison-guide",
            "transactional": "product-how-to",
            "informational": "role-guide",
        }
        return mapping.get(plan.intent, "comparison-guide")

    def to_research_snapshot(self, dataset: ResearchDataset, opportunity_id: int = 1) -> dict:
        sources = []
        for s in dataset.sources:
            source = normalize_source(
                source_url=s.get("source_url", ""),
                source_type=s.get("source_type", "fixture"),
                excerpt=s.get("excerpt", ""),
                confidence=s.get("confidence", 0.8),
                collector=s.get("collector", "research_agent"),
                metadata=s.get("metadata", {}),
            )
            sources.append(source)

        snapshot = create_research_snapshot(
            opportunity_id=opportunity_id,
            sources=sources,
            data_hash=self._compute_data_hash(dataset),
            provider="research_agent",
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
        import hashlib
        parts = [dataset.primary_keyword, dataset.intent, str(len(dataset.sources)), str(len(dataset.content_gaps))]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def run_full_cycle(self, keyword: str, intent: str = "informational", opportunity_id: int = 1) -> dict:
        plan = self.plan_research(keyword, intent)
        dataset = self.investigate(plan)
        snapshot = self.to_research_snapshot(dataset, opportunity_id)
        return {"plan": plan, "dataset": dataset, "snapshot": snapshot}


def create_agent(use_mcp: bool = False) -> ResearchAgent:
    return ResearchAgent(use_mcp=use_mcp)
