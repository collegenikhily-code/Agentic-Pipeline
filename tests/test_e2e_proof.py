"""Tests for E2E proof pipeline fixes."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from seo_aeo_geo_pipeline.template_layer.template_spec import load_template_body


class TestTemplateSpecNoPlaceholders:
    """Verify template specs contain structure, not fake content."""

    def test_comparison_guide_has_no_option_a(self):
        body = load_template_body("comparison-guide")
        assert "Option A" not in body
        assert "Option B" not in body
        assert "Option C" not in body

    def test_comparison_guide_has_structure(self):
        body = load_template_body("comparison-guide")
        assert "Introduction" in body
        assert "Criteria" in body or "Evaluation Criteria" in body
        assert "Top Picks" in body
        assert "Comparison Table" in body
        assert "How to Choose" in body
        assert "FAQ" in body

    def test_alternatives_has_no_option_a(self):
        body = load_template_body("alternatives")
        assert "Option A" not in body
        assert "Option B" not in body
        assert "Option C" not in body

    def test_best_listicle_has_no_option_a(self):
        body = load_template_body("best-listicle")
        assert "Option A" not in body
        assert "Option B" not in body
        assert "Option C" not in body

    def test_role_guide_has_no_option_a(self):
        body = load_template_body("role-guide")
        assert "Option A" not in body

    def test_problem_solution_has_no_option_a(self):
        body = load_template_body("problem-solution")
        assert "Option A" not in body

    def test_programmatic_entity_has_no_option_a(self):
        body = load_template_body("programmatic-entity")
        assert "Option A" not in body

    def test_all_templates_have_format_placeholders(self):
        """All templates must accept dynamic injection via format strings."""
        for name in ["comparison-guide", "alternatives", "best-listicle",
                      "role-guide", "problem-solution", "programmatic-entity"]:
            body = load_template_body(name)
            assert "{site_name}" in body or "{research_context}" in body, \
                f"Template {name} missing format placeholders"


class TestPSEOEngineAdapterNoEspresso:
    """Verify espresso fallback is removed."""

    def test_discover_returns_empty_opportunities(self):
        from seo_aeo_geo_pipeline.adapters.pseo_engine_adapter import discover
        result = discover("dummy.yaml", dry_run=True)
        assert result["opportunities"] == []
        assert result["dry_run"] is True

    def test_discover_no_espresso_keyword(self):
        from seo_aeo_geo_pipeline.adapters.pseo_engine_adapter import discover
        result = discover("dummy.yaml", dry_run=True)
        for opp in result["opportunities"]:
            assert "espresso" not in opp.get("keyword", "").lower()


class TestE2ENoHardcodedKeywords:
    """Verify E2E proof does not contain hardcoded demo keywords."""

    def test_run_e2e_proof_imports(self):
        """run_e2e_proof should import without hardcoded keywords in module scope."""
        import importlib
        import run_e2e_proof
        importlib.reload(run_e2e_proof)
        # Should not have PAGES constant with demo keywords
        assert not hasattr(run_e2e_proof, 'PAGES') or run_e2e_proof.PAGES is None or len(run_e2e_proof.PAGES) == 0

    def test_load_pages_from_opportunities(self):
        from run_e2e_proof import load_pages_from_opportunities
        opps = [
            {"primary_keyword": "test keyword", "intent": "commercial", "search_volume": 100},
            {"primary_keyword": "another keyword", "intent": "informational", "search_volume": 200},
        ]
        pages = load_pages_from_opportunities(opps, max_pages=2)
        assert len(pages) == 2
        assert pages[0]["keyword"] == "test keyword"
        assert pages[1]["keyword"] == "another keyword"

    def test_load_pages_respects_max(self):
        from run_e2e_proof import load_pages_from_opportunities
        opps = [
            {"primary_keyword": "kw1", "intent": "commercial"},
            {"primary_keyword": "kw2", "intent": "commercial"},
            {"primary_keyword": "kw3", "intent": "commercial"},
        ]
        pages = load_pages_from_opportunities(opps, max_pages=1)
        assert len(pages) == 1

    def test_load_pages_skips_empty_keywords(self):
        from run_e2e_proof import load_pages_from_opportunities
        opps = [
            {"primary_keyword": "", "intent": "commercial"},
            {"primary_keyword": "valid keyword", "intent": "informational"},
        ]
        pages = load_pages_from_opportunities(opps)
        assert len(pages) == 1
        assert pages[0]["keyword"] == "valid keyword"


class TestResearchAgentNoDemoCompetitors:
    """Verify research agent does not return hardcoded demo competitors."""

    def test_derive_competitors_returns_empty(self):
        from seo_aeo_geo_pipeline.research.agents.research_agent import ResearchAgent
        agent = ResearchAgent()
        competitors = agent._derive_competitors("best espresso machines", "commercial")
        assert competitors == []

    def test_derive_competitors_returns_empty_for_crm(self):
        from seo_aeo_geo_pipeline.research.agents.research_agent import ResearchAgent
        agent = ResearchAgent()
        competitors = agent._derive_competitors("best CRM for textile", "commercial")
        assert competitors == []


class TestUseCaseCapabilityTemplate:
    """Verify use-case-capability template exists and has correct structure."""

    def test_template_body_exists(self):
        body = load_template_body("use-case-capability")
        assert body
        assert "Use-Case" in body or "use-case" in body

    def test_template_body_has_required_components(self):
        body = load_template_body("use-case-capability")
        assert "quick_answer" in body
        assert "capabilities" in body
        assert "workflow_steps" in body
        assert "use_cases" in body
        assert "integrations" in body
        assert "benefits" in body
        assert "faq" in body
        assert "cta" in body

    def test_template_body_has_format_placeholders(self):
        body = load_template_body("use-case-capability")
        assert "{site_name}" in body
        assert "{research_context}" in body

    def test_template_body_no_fake_content(self):
        body = load_template_body("use-case-capability")
        assert "Option A" not in body
        assert "Option B" not in body
        assert "Option C" not in body
        assert "espresso" not in body.lower()
        assert "textile" not in body.lower()


class TestUseCaseCapabilitySchema:
    """Verify UseCaseCapabilityArticle schema validates correctly."""

    def test_schema_imports(self):
        from pseo.schemas.articles import UseCaseCapabilityArticle
        assert UseCaseCapabilityArticle is not None

    def test_schema_registry_contains_use_case(self):
        from pseo.schemas.articles import SCHEMA_REGISTRY
        assert "use-case-capability" in SCHEMA_REGISTRY

    def test_schema_validates_minimal(self):
        from pseo.schemas.articles import UseCaseCapabilityArticle
        article = UseCaseCapabilityArticle(
            h1="Test Page",
            quick_answer="This is a test.",
            capabilities=[{"title": "Cap 1", "description": "Desc 1"}],
            workflow_steps=[{"step_number": 1, "title": "Step 1", "description": "Do something"}],
            use_cases=[{"title": "UC 1", "description": "Use case 1"}],
            integrations=[{"name": "Integration 1"}],
            benefits=[{"title": "Benefit 1", "description": "Benefit desc"}],
            faq=[{"question": "Q1", "answer": "A1"}],
            cta={"heading": "CTA", "body": "Body", "button_label": "Click"},
            external_citations=[{"source": "Source 1"}],
        )
        assert article.h1 == "Test Page"
        assert len(article.capabilities) == 1
        assert len(article.workflow_steps) == 1
        assert len(article.use_cases) == 1
        assert len(article.integrations) == 1
        assert len(article.benefits) == 1
        assert len(article.faq) == 1
        assert article.cta.heading == "CTA"

    def test_schema_validates_with_defaults(self):
        from pseo.schemas.articles import UseCaseCapabilityArticle
        article = UseCaseCapabilityArticle(
            h1="Test",
            quick_answer="Test answer",
            capabilities=[],
            workflow_steps=[],
            use_cases=[],
            integrations=[],
            benefits=[],
            faq=[],
            cta={"heading": "", "body": "", "button_label": ""},
            external_citations=[],
        )
        assert article.related_pages == []
        assert article.information_gain == ""
        assert article.image_specs == []


class TestOpportunityPageTypeMapping:
    """Verify opportunity-to-page-type classification uses multi-signal logic."""

    def _make_cluster(self, primary, keywords=None, intent="informational", serp=None, competitors=None):
        from seo_aeo_geo_pipeline.discovery.models import KeywordCluster
        return KeywordCluster(
            cluster_id="test",
            primary_keyword=primary,
            keywords=keywords or [primary],
            dominant_intent=intent,
            total_search_volume=1000,
            avg_difficulty=50.0,
            competitor_pages=competitors or [],
            supporting_questions=[],
            serp_features=serp or [],
        )

    def test_comparison_vs(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster("A vs B", ["a vs b", "a versus b"])
        assert _detect_page_type(cluster, []) == "comparison-guide"

    def test_alternatives(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster("alternative to X", ["alternative to x", "similar to x"])
        assert _detect_page_type(cluster, []) == "alternatives-page"

    def test_use_case_keyword(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster(
            "workflow automation for teams",
            ["workflow automation", "automate workflow"],
            intent="informational",
        )
        assert _detect_page_type(cluster, []) == "use-case-capability"

    def test_integration_keyword(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster(
            "integration with CRM",
            ["integration with crm", "connect to crm"],
            intent="informational",
        )
        # integration-page is a future archetype, not yet implemented.
        # Integration signals route to use-case-capability.
        assert _detect_page_type(cluster, []) == "use-case-capability"

    def test_commercial_product_tool(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster(
            "best project management tool",
            ["project management tool", "best project management software"],
            intent="commercial",
        )
        assert _detect_page_type(cluster, []) == "comparison-guide"

    def test_entity_reference(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster(
            "what is facebook business manager",
            ["what is facebook business manager", "definition of facebook business manager"],
            intent="informational",
        )
        assert _detect_page_type(cluster, []) == "reference-page"

    def test_how_to_guide(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster(
            "how to use facebook ads",
            ["how to use facebook ads", "facebook ads tutorial"],
            intent="informational",
        )
        assert _detect_page_type(cluster, []) == "guide"

    def test_transactional_default(self):
        from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
        cluster = self._make_cluster(
            "buy seo tools",
            ["buy seo tools"],
            intent="transactional",
        )
        assert _detect_page_type(cluster, []) == "product-page"


class TestComponentRendering:
    """Verify use-case-capability renderer produces correct HTML structure."""

    def test_renderer_imports(self):
        from pseo.render import render_article
        assert render_article is not None

    def test_renderer_registry_contains_use_case(self):
        from pseo.render import _RENDER_REGISTRY
        assert "use-case-capability" in _RENDER_REGISTRY

    def test_render_use_case_capability_produces_html(self):
        from pseo.render import render_article
        structured_data = {
            "h1": "Test Product",
            "quick_answer": "This product helps teams automate workflows.",
            "capabilities": [
                {"title": "Automation", "description": "Automate repetitive tasks."},
                {"title": "Analytics", "description": "Track performance metrics."},
            ],
            "workflow_steps": [
                {"step_number": 1, "title": "Connect", "description": "Connect your tools."},
                {"step_number": 2, "title": "Configure", "description": "Set up workflows."},
            ],
            "use_cases": [
                {"title": "Marketing", "description": "Automate marketing campaigns.", "example": "Social media posting", "result": "3x engagement"},
            ],
            "integrations": [
                {"name": "Slack", "category": "Communication", "description": "Send notifications"},
                {"name": "HubSpot", "category": "CRM", "description": "Sync contacts"},
            ],
            "benefits": [
                {"title": "Save Time", "description": "Reduce manual work by 60%.", "metric": "60%"},
            ],
            "faq": [
                {"question": "What is this?", "answer": "It's a workflow automation platform."},
            ],
            "cta": {
                "heading": "Ready to automate?",
                "body": "Start your free trial today.",
                "button_label": "Get Started",
                "button_url": "",
            },
            "external_citations": [{"source": "Gartner"}],
        }
        html = render_article("use-case-capability", structured_data)
        assert "<h1>Test Product</h1>" in html
        assert "Automation" in html
        assert "Analytics" in html
        assert "Connect" in html
        assert "Configure" in html
        assert "Marketing" in html
        assert "Slack" in html
        assert "HubSpot" in html
        assert "Save Time" in html
        assert "What is this?" in html
        assert "Ready to automate?" in html
        assert "Get Started" in html

    def test_render_use_case_empty_cta_url(self):
        """CTA button should render even without URL (disabled state)."""
        from pseo.render import render_article
        structured_data = {
            "h1": "Test",
            "quick_answer": "Test answer",
            "capabilities": [],
            "workflow_steps": [],
            "use_cases": [],
            "integrations": [],
            "benefits": [],
            "faq": [],
            "cta": {"heading": "CTA", "body": "Body", "button_label": "Click", "button_url": ""},
            "external_citations": [],
        }
        html = render_article("use-case-capability", structured_data)
        assert "Click" in html
        assert "uc-cta-btn-disabled" in html

    def test_render_use_case_no_invented_urls(self):
        """Integration URLs should only appear when explicitly provided."""
        from pseo.render import render_article
        structured_data = {
            "h1": "Test",
            "quick_answer": "Test answer",
            "capabilities": [],
            "workflow_steps": [],
            "use_cases": [],
            "integrations": [{"name": "Tool", "category": "CRM", "description": "A tool"}],
            "benefits": [],
            "faq": [],
            "cta": {"heading": "", "body": "", "button_label": ""},
            "external_citations": [],
        }
        html = render_article("use-case-capability", structured_data)
        assert "Tool" in html
        assert "http" not in html.split("integrations")[1].split("</section>")[0] if "integrations" in html else True


class TestComponentValidation:
    """Verify component structural validation in unified_gate."""

    def test_validation_imports(self):
        from seo_aeo_geo_pipeline.gates.unified_gate import _validate_component_structure
        assert _validate_component_structure is not None

    def test_non_uc_page_no_warnings(self):
        from seo_aeo_geo_pipeline.gates.unified_gate import _validate_component_structure
        structured_data = {"h1": "Test", "quick_answer": "Answer"}
        warnings = _validate_component_structure(structured_data)
        assert warnings == []

    def test_uc_page_missing_components(self):
        from seo_aeo_geo_pipeline.gates.unified_gate import _validate_component_structure
        structured_data = {
            "h1": "Test",
            "capabilities": [],
            "workflow_steps": [],
        }
        warnings = _validate_component_structure(structured_data)
        assert any("MISSING_COMPONENT" in w for w in warnings)
        assert any("quick_answer" in w for w in warnings)

    def test_uc_page_empty_capability(self):
        from seo_aeo_geo_pipeline.gates.unified_gate import _validate_component_structure
        structured_data = {
            "h1": "Test",
            "quick_answer": "Answer",
            "capabilities": [{"title": "", "description": ""}],
            "workflow_steps": [],
            "use_cases": [],
            "integrations": [],
            "benefits": [],
            "faq": [{"question": "Q", "answer": "A"}],
            "cta": {"heading": "H", "body": "B", "button_label": "L"},
        }
        warnings = _validate_component_structure(structured_data)
        assert any("EMPTY_FIELD" in w for w in warnings)

    def test_uc_page_placeholder_content(self):
        from seo_aeo_geo_pipeline.gates.unified_gate import _validate_component_structure
        structured_data = {
            "h1": "Best Espresso Machines",
            "quick_answer": "This is about espresso machines.",
            "capabilities": [{"title": "Option A", "description": "Description"}],
            "workflow_steps": [],
            "use_cases": [],
            "integrations": [],
            "benefits": [],
            "faq": [{"question": "Q", "answer": "A"}],
            "cta": {"heading": "H", "body": "B", "button_label": "L"},
        }
        warnings = _validate_component_structure(structured_data)
        assert any("PLACEHOLDER_CONTENT" in w for w in warnings)
