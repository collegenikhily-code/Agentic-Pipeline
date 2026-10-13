"""Tests for DeepResearchAgent."""

import pytest
from unittest.mock import MagicMock, patch
from seo_aeo_geo_pipeline.research.deep_research import DeepResearchAgent, _parse_json_from_llm
from seo_aeo_geo_pipeline.research.agents.research_agent import ResearchDataset, ResearchPlan
from seo_aeo_geo_pipeline.research.dify_rag import DifyRAGClient, KnowledgeRetrieval


class TestParseJsonFromLlm:
    def test_direct_json(self):
        result = _parse_json_from_llm('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_fence(self):
        result = _parse_json_from_llm('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_json_with_surrounding_text(self):
        result = _parse_json_from_llm('Here is the result: {"key": "value"} done.')
        assert result == {"key": "value"}

    def test_invalid_json(self):
        result = _parse_json_from_llm("not json at all")
        assert result == {}


class TestDeepResearchAgent:
    def test_init_defaults(self):
        agent = DeepResearchAgent()
        assert agent.model == "openrouter/inclusionai/ling-3.0-flash-sante"
        assert not agent.dify.is_configured

    def test_init_with_dify(self):
        dify = DifyRAGClient(api_key="test", dataset_id="test-dataset")
        agent = DeepResearchAgent(dify_client=dify)
        assert agent.dify.is_configured

    def test_plan_research_fallback(self):
        """When LLM fails, plan should use fallback questions."""
        agent = DeepResearchAgent()
        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", side_effect=RuntimeError("no llm")):
            plan = agent.plan_research("test keyword", "commercial")
            assert isinstance(plan, ResearchPlan)
            assert plan.primary_keyword == "test keyword"
            assert plan.intent == "commercial"
            assert len(plan.sub_questions) >= 1

    def test_plan_research_parses_llm_response(self):
        agent = DeepResearchAgent()
        mock_response = '{"sub_questions": [{"question": "What is X?", "source_types": ["web"]}], "target_audience": "developers", "content_gaps": ["gap1"], "competing_pages": ["page1"]}'
        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", return_value=mock_response):
            plan = agent.plan_research("test keyword", "informational")
            assert len(plan.sub_questions) == 1
            assert plan.sub_questions[0].question == "What is X?"
            assert plan.target_audience == "developers"

    def test_investigate_calls_llm_for_each_question(self):
        agent = DeepResearchAgent()
        from seo_aeo_geo_pipeline.research.agents.research_agent import SubQuestion
        plan = ResearchPlan(
            primary_keyword="test",
            intent="informational",
            sub_questions=[SubQuestion(id="sq_1", question="What is test?", intent="informational", source_types=["web"])],
        )

        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", return_value="Test is a thing."):
            dataset = agent.investigate(plan)
            assert isinstance(dataset, ResearchDataset)
            assert len(dataset.sources) >= 1

    def test_recommend_page_type(self):
        agent = DeepResearchAgent()
        plan = ResearchPlan(primary_keyword="x", intent="commercial")
        assert agent._recommend_page_type(plan) == "comparison-guide"
        plan.intent = "transactional"
        assert agent._recommend_page_type(plan) == "product-how-to"
        plan.intent = "informational"
        assert agent._recommend_page_type(plan) == "role-guide"

    def test_to_research_snapshot(self):
        agent = DeepResearchAgent()
        dataset = ResearchDataset(
            primary_keyword="test",
            intent="informational",
            sources=[],
            content_gaps=["gap1"],
        )
        snapshot = agent.to_research_snapshot(dataset, opportunity_id=42)
        assert snapshot["opportunity_id"] == 42
        assert snapshot["provider"] == "deep_research_agent"
        assert snapshot["primary_keyword"] == "test"

    def test_run_full_cycle_returns_dict(self):
        agent = DeepResearchAgent()
        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", side_effect=RuntimeError("no llm")):
            result = agent.run_full_cycle("test keyword", "informational", opportunity_id=1)
            assert "plan" in result
            assert "dataset" in result
            assert "snapshot" in result
            assert isinstance(result["plan"], ResearchPlan)
            assert isinstance(result["dataset"], ResearchDataset)

    def test_investigate_with_dify_knowledge(self):
        """When Dify has results, they should appear in sources."""
        dify = DifyRAGClient(api_key="test", dataset_id="test-dataset")
        agent = DeepResearchAgent(dify_client=dify)

        from seo_aeo_geo_pipeline.research.dify_rag import RetrievalResult
        mock_knowledge = KnowledgeRetrieval(
            query="test",
            results=[RetrievalResult(content="dify content", source_url="http://dify.example", score=0.9)],
            total_results=1,
        )

        plan = ResearchPlan(primary_keyword="test", intent="informational", sub_questions=[])

        with patch.object(dify, "retrieve", return_value=mock_knowledge):
            dataset = agent.investigate(plan)
            dify_sources = [s for s in dataset.sources if s.get("collector") == "dify_rag"]
            assert len(dify_sources) == 1

    def test_investigate_without_competitor_intel(self):
        """Pipeline works correctly when competitor_intel is None."""
        agent = DeepResearchAgent(competitor_intel=None)
        assert agent.competitor_intel is None

        from seo_aeo_geo_pipeline.research.agents.research_agent import SubQuestion
        plan = ResearchPlan(
            primary_keyword="test",
            intent="informational",
            sub_questions=[SubQuestion(id="sq_1", question="What is test?", intent="informational", source_types=["web"])],
        )

        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", return_value="Test is a thing."):
            dataset = agent.investigate(plan)
            assert isinstance(dataset, ResearchDataset)
            # Should have LLM source but no competitor_intelligence source
            comp_sources = [s for s in dataset.sources if s.get("source_type") == "competitor_intelligence"]
            assert len(comp_sources) == 0
            llm_sources = [s for s in dataset.sources if s.get("source_type") == "llm_research"]
            assert len(llm_sources) >= 1

    def test_call_llm_rate_limit_error(self):
        """_call_llm raises RuntimeError with RATE_LIMIT prefix on429."""
        from seo_aeo_geo_pipeline.research.deep_research import _call_llm

        # Simulate litellm RateLimitError
        mock_error = Exception("RateLimitError: OpenrouterException - rate limit exceeded")
        with patch("litellm.completion", side_effect=mock_error):
            with pytest.raises(RuntimeError, match="RATE_LIMIT"):
                _call_llm("test prompt")

    def test_call_llm_auth_error_not_ratelimit(self):
        """_call_llm raises generic RuntimeError for non-rate-limit auth errors."""
        from seo_aeo_geo_pipeline.research.deep_research import _call_llm

        mock_error = Exception("AuthenticationError: invalid api key")
        with patch("litellm.completion", side_effect=mock_error):
            with pytest.raises(RuntimeError, match="LLM call failed"):
                _call_llm("test prompt")

    def test_investigate_rate_limit_partial_success(self):
        """When rate-limited mid-investigation, completed questions are kept."""
        agent = DeepResearchAgent(competitor_intel=None)

        from seo_aeo_geo_pipeline.research.agents.research_agent import SubQuestion
        plan = ResearchPlan(
            primary_keyword="test",
            intent="informational",
            sub_questions=[
                SubQuestion(id="sq_1", question="Q1?", intent="informational", source_types=["web"]),
                SubQuestion(id="sq_2", question="Q2?", intent="informational", source_types=["web"]),
            ],
        )

        # First call succeeds, second hits rate limit
        call_count = 0
        def mock_llm(prompt, model="", max_tokens=0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Answer 1"
            raise RuntimeError("RATE_LIMIT: quota exhausted")

        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", side_effect=mock_llm):
            dataset = agent.investigate(plan)
            # First question answered, second skipped
            assert len(dataset.questions_answered) == 1
            assert "Q1?" in dataset.questions_answered
            assert len(dataset.content_gaps) == 1

    def test_completion_status_complete(self):
        """Complete research → completion_status == 'complete'."""
        agent = DeepResearchAgent(competitor_intel=None)
        from seo_aeo_geo_pipeline.research.agents.research_agent import SubQuestion
        plan = ResearchPlan(
            primary_keyword="test",
            intent="informational",
            sub_questions=[
                SubQuestion(id="sq_1", question="Q1?", intent="informational", source_types=["web"]),
                SubQuestion(id="sq_2", question="Q2?", intent="informational", source_types=["web"]),
            ],
        )
        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", return_value="Answer"):
            dataset = agent.investigate(plan)
            assert dataset.completion_status == "complete"

    def test_completion_status_partial_rate_limited(self):
        """Rate-limited research → completion_status == 'partial_rate_limited'."""
        agent = DeepResearchAgent(competitor_intel=None)
        from seo_aeo_geo_pipeline.research.agents.research_agent import SubQuestion
        plan = ResearchPlan(
            primary_keyword="test",
            intent="informational",
            sub_questions=[
                SubQuestion(id="sq_1", question="Q1?", intent="informational", source_types=["web"]),
                SubQuestion(id="sq_2", question="Q2?", intent="informational", source_types=["web"]),
            ],
        )
        call_count = 0
        def mock_llm(prompt, model="", max_tokens=0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Answer 1"
            raise RuntimeError("RATE_LIMIT: quota exhausted")

        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", side_effect=mock_llm):
            dataset = agent.investigate(plan)
            assert dataset.completion_status == "partial_rate_limited"
            assert len(dataset.questions_answered) == 1

    def test_completion_status_partial_error(self):
        """Non-rate-limit error on subset → completion_status == 'partial_error'."""
        agent = DeepResearchAgent(competitor_intel=None)
        from seo_aeo_geo_pipeline.research.agents.research_agent import SubQuestion
        plan = ResearchPlan(
            primary_keyword="test",
            intent="informational",
            sub_questions=[
                SubQuestion(id="sq_1", question="Q1?", intent="informational", source_types=["web"]),
                SubQuestion(id="sq_2", question="Q2?", intent="informational", source_types=["web"]),
            ],
        )
        call_count = 0
        def mock_llm(prompt, model="", max_tokens=0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Answer 1"
            raise RuntimeError("LLM call failed: connection timeout")

        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", side_effect=mock_llm):
            dataset = agent.investigate(plan)
            assert dataset.completion_status == "partial_error"
            assert len(dataset.questions_answered) == 1

    def test_snapshot_persists_completion_status(self):
        """Snapshot includes completion_status field."""
        agent = DeepResearchAgent()
        dataset = ResearchDataset(
            primary_keyword="test",
            intent="informational",
            completion_status="partial_rate_limited",
            questions_answered=["Q1?"],
            content_gaps=["Q2?"],
        )
        snapshot = agent.to_research_snapshot(dataset, opportunity_id=1)
        assert snapshot["completion_status"] == "partial_rate_limited"

    def test_snapshot_complete_status(self):
        """Complete snapshot has completion_status == 'complete'."""
        agent = DeepResearchAgent()
        dataset = ResearchDataset(
            primary_keyword="test",
            intent="informational",
            completion_status="complete",
        )
        snapshot = agent.to_research_snapshot(dataset, opportunity_id=1)
        assert snapshot["completion_status"] == "complete"

    def test_rate_limit_preserves_completed_evidence(self):
        """Rate-limited investigation preserves evidence from completed questions."""
        agent = DeepResearchAgent(competitor_intel=None)
        from seo_aeo_geo_pipeline.research.agents.research_agent import SubQuestion
        plan = ResearchPlan(
            primary_keyword="test",
            intent="informational",
            sub_questions=[
                SubQuestion(id="sq_1", question="Q1?", intent="informational", source_types=["web"]),
                SubQuestion(id="sq_2", question="Q2?", intent="informational", source_types=["web"]),
            ],
        )
        call_count = 0
        def mock_llm(prompt, model="", max_tokens=0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Detailed answer about topic"
            raise RuntimeError("RATE_LIMIT: quota exhausted")

        with patch("seo_aeo_geo_pipeline.research.deep_research._call_llm", side_effect=mock_llm):
            dataset = agent.investigate(plan)
            # Completed evidence preserved
            assert "Q1?" in dataset.evidence_by_claim
            assert "Detailed answer about topic" in dataset.evidence_by_claim["Q1?"][0]
            # Sources include the completed LLM source
            llm_sources = [s for s in dataset.sources if s["source_type"] == "llm_research"]
            assert len(llm_sources) == 1


class TestResearchCompleteGate:
    """Tests for the check_research_complete gate function."""

    def test_complete_passes(self):
        from seo_aeo_geo_pipeline.gates.gate2_evidence_pagespec import check_research_complete
        assert check_research_complete({"completion_status": "complete"}) is True

    def test_partial_rate_limited_blocks(self):
        from seo_aeo_geo_pipeline.gates.gate2_evidence_pagespec import check_research_complete
        assert check_research_complete({"completion_status": "partial_rate_limited"}) is False

    def test_partial_error_blocks(self):
        from seo_aeo_geo_pipeline.gates.gate2_evidence_pagespec import check_research_complete
        assert check_research_complete({"completion_status": "partial_error"}) is False

    def test_missing_status_blocks(self):
        """Backward compat: missing status → NOT complete (safe default)."""
        from seo_aeo_geo_pipeline.gates.gate2_evidence_pagespec import check_research_complete
        assert check_research_complete({}) is False

    def test_unknown_status_blocks(self):
        """Unknown status value → NOT complete (safe default)."""
        from seo_aeo_geo_pipeline.gates.gate2_evidence_pagespec import check_research_complete
        assert check_research_complete({"completion_status": "unknown"}) is False


class TestCatalystAdapterCompletion:
    """Tests for CATALYST adapter completion check."""

    def test_adapter_raises_on_partial(self):
        """Adapter raises RuntimeError on partial research (retryable)."""
        from seo_aeo_geo_pipeline.catalyst.adapters import create_research_fn
        from seo_aeo_geo_pipeline.models import PageJob

        agent = DeepResearchAgent(competitor_intel=None)
        research_fn = create_research_fn(agent)

        job = PageJob(job_id="j1", keyword="test", intent="informational")

        # Mock run_full_cycle to return partial result
        partial_result = {
            "snapshot": {"completion_status": "partial_rate_limited", "questions_answered": ["Q1?"]},
            "dataset": ResearchDataset(primary_keyword="test", intent="informational"),
        }
        with patch.object(agent, "run_full_cycle", return_value=partial_result):
            with pytest.raises(RuntimeError, match="Research incomplete"):
                research_fn(job)

    def test_adapter_passes_on_complete(self):
        """Adapter returns result on complete research."""
        from seo_aeo_geo_pipeline.catalyst.adapters import create_research_fn
        from seo_aeo_geo_pipeline.models import PageJob

        agent = DeepResearchAgent(competitor_intel=None)
        research_fn = create_research_fn(agent)

        job = PageJob(job_id="j1", keyword="test", intent="informational")

        complete_result = {
            "snapshot": {"completion_status": "complete", "questions_answered": ["Q1?"]},
            "dataset": ResearchDataset(primary_keyword="test", intent="informational"),
        }
        with patch.object(agent, "run_full_cycle", return_value=complete_result):
            result = research_fn(job)
            assert result["snapshot"]["completion_status"] == "complete"
