"""Tests for HyperText template selector adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from seo_aeo_geo_pipeline.template_layer.hypertext_selector import (
    HyperTextClient,
    HyperTextSelectionInput,
    HyperTextSelectionResult,
    HyperTextSelectorAdapter,
    TemplateSelectionContext,
    TemplateSelectorFallback,
)
from seo_aeo_geo_pipeline.template_layer.registry import (
    TemplateRegistry,
    register_all_templates,
)
from seo_aeo_geo_pipeline.config import Settings


@pytest.fixture
def registry() -> TemplateRegistry:
    reg = TemplateRegistry()
    register_all_templates(reg)
    return reg


@pytest.fixture
def config() -> Settings:
    return Settings()


@pytest.fixture
def selection_context() -> TemplateSelectionContext:
    return TemplateSelectionContext(
        job_id="test-job-001",
        run_id="test-run-001",
        keyword="best CRM for textile manufacturers",
        intent="commercial",
        page_type="comparison-guide",
        content_type="article",
        target_audience="buyers evaluating options",
        aeo_geo_requirements=["comparison table", "FAQ schema"],
        schema_markup_needs=["Product", "FAQPage"],
        differentiation_strategy="Compare across price, features, usability",
        competing_analysis=[{"page": "Competitor A"}, {"page": "Competitor B"}],
        questions_answered=["What is the best CRM?", "How do they compare?"],
        research_sources_count=10,
        completion_status="complete",
    )


class TestHyperTextSelectionInput:
    def test_defaults(self):
        inp = HyperTextSelectionInput(keyword="test", intent="informational", page_type="role-guide")
        assert inp.keyword == "test"
        assert inp.intent == "informational"
        assert inp.page_type == "role-guide"
        assert inp.content_type == ""
        assert inp.aeo_geo_requirements == []
        assert inp.completion_status == "complete"

    def test_full_input(self):
        inp = HyperTextSelectionInput(
            keyword="test",
            intent="commercial",
            page_type="comparison-guide",
            content_type="article",
            target_audience="buyers",
            aeo_geo_requirements=["table", "faq"],
            schema_markup_needs=["Product"],
            differentiation_strategy="differentiate",
            competing_analysis=[{"page": "A"}],
            questions_answered=["Q1"],
            research_sources_count=5,
            completion_status="partial_rate_limited",
        )
        assert inp.content_type == "article"
        assert inp.aeo_geo_requirements == ["table", "faq"]
        assert inp.completion_status == "partial_rate_limited"


class TestHyperTextClient:
    def test_not_configured_by_default(self):
        client = HyperTextClient(api_key="", base_url="https://api.example.com")
        assert not client.is_configured

    def test_configured_with_key(self):
        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        assert client.is_configured

    def test_select_template_raises_when_not_configured(self):
        client = HyperTextClient(api_key="", base_url="https://api.example.com")
        inp = HyperTextSelectionInput(keyword="test", intent="info", page_type="role-guide")
        with pytest.raises(RuntimeError, match="HyperText not configured"):
            client.select_template(inp)

    @patch("requests.Session")
    def test_select_template_success(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "template_name": "comparison-guide",
            "template_family": "comparison",
            "confidence": 0.95,
            "request_id": "req-123",
        }
        mock_resp.raise_for_status.return_value = None
        mock_session.post.return_value = mock_resp

        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        inp = HyperTextSelectionInput(keyword="test", intent="commercial", page_type="comparison-guide")
        result = client.select_template(inp)

        assert result.source == "hypertext"
        assert result.template_name == "comparison-guide"
        assert result.template_family == "comparison"
        assert result.confidence == 0.95
        assert result.hypertext_request_id == "req-123"
        assert result.hypertext_latency_ms is not None
        mock_session.post.assert_called_once()

    @patch("requests.Session")
    def test_select_template_missing_template_name_raises(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"template_family": "comparison", "confidence": 0.9}
        mock_resp.raise_for_status.return_value = None
        mock_session.post.return_value = mock_resp

        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        inp = HyperTextSelectionInput(keyword="test", intent="commercial", page_type="comparison-guide")
        with pytest.raises(ValueError, match="missing 'template_name'"):
            client.select_template(inp)

    @patch("requests.Session")
    def test_select_template_connection_error(self, mock_session_class):
        import requests
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.post.side_effect = requests.exceptions.ConnectionError("connection failed")

        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        inp = HyperTextSelectionInput(keyword="test", intent="commercial", page_type="comparison-guide")
        with pytest.raises(RuntimeError, match="HyperText connection failed"):
            client.select_template(inp)

    @patch("requests.Session")
    def test_select_template_timeout(self, mock_session_class):
        import requests
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.post.side_effect = requests.exceptions.Timeout("timeout")

        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        inp = HyperTextSelectionInput(keyword="test", intent="commercial", page_type="comparison-guide")
        with pytest.raises(RuntimeError, match="HyperText request timed out"):
            client.select_template(inp)

    @patch("requests.Session")
    def test_select_template_http_error(self, mock_session_class):
        import requests
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        http_error = requests.exceptions.HTTPError("401", response=mock_resp)
        mock_session.post.side_effect = http_error

        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        inp = HyperTextSelectionInput(keyword="test", intent="commercial", page_type="comparison-guide")
        with pytest.raises(RuntimeError, match="HyperText HTTP error 401"):
            client.select_template(inp)


class TestTemplateSelectorFallback:
    def test_select_returns_valid_template(self, registry, config, selection_context):
        fallback = TemplateSelectorFallback(registry, config)
        result = fallback.select(selection_context)

        assert result.source == "fallback"
        assert result.template_name in [s.name for s in registry.list_all()]
        assert result.template_family in registry.families()
        assert result.confidence == 0.9
        assert result.fallback_reason is not None

    def test_select_commercial_intent_maps_to_comparison_family(self, registry, config):
        context = TemplateSelectionContext(
            job_id="j1", run_id="r1", keyword="best CRM", intent="commercial",
            page_type="comparison-guide", content_type="article",
            target_audience="", aeo_geo_requirements=[], schema_markup_needs=[],
            differentiation_strategy="", competing_analysis=[], questions_answered=[],
            research_sources_count=0, completion_status="complete",
        )
        fallback = TemplateSelectorFallback(registry, config)
        result = fallback.select(context)
        assert result.template_family == "comparison"

    def test_select_informational_intent_maps_to_role_guide_family(self, registry, config):
        context = TemplateSelectionContext(
            job_id="j1", run_id="r1", keyword="what is SEO", intent="informational",
            page_type="role-guide", content_type="article",
            target_audience="", aeo_geo_requirements=[], schema_markup_needs=[],
            differentiation_strategy="", competing_analysis=[], questions_answered=[],
            research_sources_count=0, completion_status="complete",
        )
        fallback = TemplateSelectorFallback(registry, config)
        result = fallback.select(context)
        assert result.template_family == "role-guide"

    def test_select_transactional_intent_maps_to_problem_solution_family(self, registry, config):
        context = TemplateSelectionContext(
            job_id="j1", run_id="r1", keyword="how to integrate ERP", intent="transactional",
            page_type="product-how-to", content_type="article",
            target_audience="", aeo_geo_requirements=[], schema_markup_needs=[],
            differentiation_strategy="", competing_analysis=[], questions_answered=[],
            research_sources_count=0, completion_status="complete",
        )
        fallback = TemplateSelectorFallback(registry, config)
        result = fallback.select(context)
        assert result.template_family == "problem-solution"


class TestHyperTextSelectorAdapter:
    def test_fallback_when_hypertext_not_configured(self, registry, config, selection_context):
        adapter = HyperTextSelectorAdapter(registry, config, hypertext_client=HyperTextClient(api_key=""))
        assert not adapter.hypertext_configured

        result = adapter.select(selection_context)

        assert result.source == "fallback"
        assert result.fallback_reason == "hypertext_not_configured"
        assert result.template_name in [s.name for s in registry.list_all()]

    def test_fallback_when_hypertext_fails(self, registry, config, selection_context):
        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        adapter = HyperTextSelectorAdapter(registry, config, hypertext_client=client)

        with patch.object(client, "select_template", side_effect=RuntimeError("API down")):
            result = adapter.select(selection_context)

        assert result.source == "fallback"
        assert "hypertext_error" in result.fallback_reason

    def test_hypertext_success_validates_against_registry(self, registry, config, selection_context):
        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        adapter = HyperTextSelectorAdapter(registry, config, hypertext_client=client)

        with patch.object(client, "select_template", return_value=HyperTextSelectionResult(
            template_name="comparison-guide",
            template_family="comparison",
            confidence=0.95,
            source="hypertext",
            hypertext_request_id="req-123",
        )):
            result = adapter.select(selection_context)

        assert result.source == "hypertext"
        assert result.template_name == "comparison-guide"

    def test_hypertext_unknown_template_falls_back(self, registry, config, selection_context):
        client = HyperTextClient(api_key="test-key", base_url="https://api.example.com")
        adapter = HyperTextSelectorAdapter(registry, config, hypertext_client=client)

        with patch.object(client, "select_template", return_value=HyperTextSelectionResult(
            template_name="nonexistent_template",
            template_family="comparison",
            confidence=0.95,
            source="hypertext",
            hypertext_request_id="req-123",
        )):
            result = adapter.select(selection_context)

        assert result.source == "fallback"
        assert result.fallback_reason == "hypertext_returned_unknown_template"
        assert result.template_name in [s.name for s in registry.list_all()]

    def test_select_for_research_snapshot(self, registry, config):
        adapter = HyperTextSelectorAdapter(registry, config, hypertext_client=HyperTextClient(api_key=""))

        snapshot = {
            "primary_keyword": "best CRM for textile manufacturers",
            "intent": "commercial",
            "page_type_recommendation": "comparison-guide",
            "audience_profile": "buyers evaluating options",
            "aeo_geo_requirements": ["comparison table", "FAQ schema"],
            "schema_markup_needs": ["Product", "FAQPage"],
            "differentiation_strategy": "Compare across price, features",
            "competing_analysis": [{"page": "Competitor A"}],
            "questions_answered": ["What is the best CRM?"],
            "source_count": 10,
            "completion_status": "complete",
        }

        result = adapter.select_for_research_snapshot("job-1", "run-1", snapshot)

        assert result.source == "fallback"
        assert result.template_name in [s.name for s in registry.list_all()]

    def test_hypertext_configured_property(self, registry, config):
        adapter_configured = HyperTextSelectorAdapter(registry, config, hypertext_client=HyperTextClient(api_key="key"))
        adapter_not_configured = HyperTextSelectorAdapter(registry, config, hypertext_client=HyperTextClient(api_key=""))

        assert adapter_configured.hypertext_configured
        assert not adapter_not_configured.hypertext_configured


class TestHyperTextSelectionResult:
    def test_to_dict_compatibility(self):
        result = HyperTextSelectionResult(
            template_name="comparison-guide",
            template_family="comparison",
            confidence=0.95,
            source="hypertext",
            hypertext_request_id="req-123",
            hypertext_latency_ms=150.5,
            fallback_reason=None,
            metadata={"custom": "data"},
        )
        d = result.__dict__
        assert d["template_name"] == "comparison-guide"
        assert d["source"] == "hypertext"
        assert d["hypertext_latency_ms"] == 150.5

    def test_fallback_result_has_reason(self):
        result = HyperTextSelectionResult(
            template_name="role-guide",
            template_family="role-guide",
            confidence=0.9,
            source="fallback",
            fallback_reason="hypertext_not_configured",
        )
        assert result.source == "fallback"
        assert result.fallback_reason == "hypertext_not_configured"
        assert result.hypertext_request_id is None