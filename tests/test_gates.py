"""M1 unit tests for gate functions.

No PostgreSQL required.
"""

import pytest
from seo_aeo_geo_pipeline.gates.gate1_opportunity_qualification import qualify_opportunity
from seo_aeo_geo_pipeline.gates.gate2_evidence_pagespec import (
    check_evidence_sufficient,
    check_product_truth_aligned,
    check_page_type,
    check_required_sections,
    check_entities_identified,
    check_questions_identified,
    check_differentiation_defined,
)
from seo_aeo_geo_pipeline.gates.gate3_pseo_quality import (
    run_guardrails,
    evaluate_citability,
    gate3_result,
)
from seo_aeo_geo_pipeline.gates.gate4_aeo_geo import gate4_result


class TestGate1:
    """GATE 1: Opportunity Qualification."""

    def test_qualify_with_valid_keyword_and_business_relevance(self):
        """M1: Valid keyword + business relevance → QUALIFIED."""
        result = qualify_opportunity(
            keyword="best espresso machines",
            intent="commercial",
            business_relevance=0.85,
            existing_pages=["page-about-coffee"],
            product_truth_refs=["feature-1"],
        )
        assert result == "QUALIFIED"

    def test_qualify_rejects_no_keyword(self):
        """M1: No keyword → REJECTED."""
        result = qualify_opportunity(
            keyword="",
            intent="commercial",
            business_relevance=0.85,
            existing_pages=[],
            product_truth_refs=[],
        )
        assert result == "REJECTED"

    def test_qualify_rejects_low_business_relevance(self):
        """M1: Low business relevance → REJECTED."""
        result = qualify_opportunity(
            keyword="best espresso machines",
            intent="commercial",
            business_relevance=0.1,  # too low
            existing_pages=[],
            product_truth_refs=[],
        )
        assert result == "REJECTED"

    def test_qualify_cannibalization(self):
        """M1: Keyword matches existing page → REJECTED (cannibalization)."""
        result = qualify_opportunity(
            keyword="best espresso machines",
            intent="commercial",
            business_relevance=0.85,
            existing_pages=["best espresso machines review"],  # cannibalizes
            product_truth_refs=[],
        )
        assert result == "REJECTED"


class TestGate2:
    """GATE 2: Evidence + Page Specification."""

    def test_spec_ready_all_requirements_met(self):
        """M1: All GATE 2 requirements met → READY."""
        # Import spec_ready from gate1 (or define inline)
        from seo_aeo_geo_pipeline.gates.gate1_opportunity_qualification import spec_ready
        result = spec_ready(
            evidence_count=3,
            product_truth_aligned=True,
            page_type="comparison-guide",
            required_sections={"introduction", "body", "conclusion"},
            entities=["espresso machine", "grinder"],
            questions=["What is the best espresso machine?"],
            differentiation="Compares 5 brands with objective testing",
        )
        assert result == "READY"

    def test_spec_ready_no_evidence(self):
        """M1: No evidence → REJECTED."""
        from seo_aeo_geo_pipeline.gates.gate1_opportunity_qualification import spec_ready
        result = spec_ready(
            evidence_count=0,
            product_truth_aligned=True,
            page_type="comparison-guide",
            required_sections={"introduction"},
            entities=[],
            questions=[],
            differentiation="Compares 5 brands with objective testing",
        )
        assert result == "REJECTED"

    def test_spec_ready_no_differentiation(self):
        """M1: No differentiation strategy → REJECTED."""
        from seo_aeo_geo_pipeline.gates.gate1_opportunity_qualification import spec_ready
        result = spec_ready(
            evidence_count=3,
            product_truth_aligned=True,
            page_type="comparison-guide",
            required_sections={"introduction"},
            entities=["espresso machine"],
            questions=["What is the best?"],
            differentiation="",
        )
        assert result == "REJECTED"


class TestGate3:
    """GATE 3: pSEO Integrity / Content Quality."""

    def test_gate3_pass_no_blocking_failures(self):
        """M1: No blocking guardrail failures + citability >= 50 → PASS."""
        guardrail = {"blocked": False, "warnings": []}
        citability = {"score": 72, "grade": "B", "passed": 3, "total": 4, "checks": []}
        result = gate3_result(guardrail, citability)
        assert result == "PASS"

    def test_gate3_reject_blocked(self):
        """M1: Blocked guardrails → REJECT."""
        guardrail = {"blocked": True, "warnings": []}
        citability = {"score": 72, "grade": "B", "passed": 3, "total": 4, "checks": []}
        result = gate3_result(guardrail, citability)
        assert result == "REJECT"

    def test_gate3_repair_low_citability(self):
        """M1: Citability < 50 → REPAIR."""
        guardrail = {"blocked": False, "warnings": []}
        citability = {"score": 45, "grade": "D", "passed": 1, "total": 4, "checks": []}
        result = gate3_result(guardrail, citability)
        assert result == "REPAIR"

    def test_run_guardrails_basic(self):
        """M1: run_guardrails returns structured report."""
        draft = {
            "h1": "Best Espresso Machines",
            "quick_answer": "Top 5 espresso machines for home use",
            "external_citations": ["source-1"],
        }
        existing_titles = []
        corpus_texts = []
        report = run_guardrails(draft, existing_titles, corpus_texts)
        assert "blocked" in report
        assert "results" in report
        assert len(report["results"]) > 0


class TestGate4:
    """GATE 4: AEO/GEO Quality."""

    def test_gate4_pass_all_checks(self):
        """M1: Citability >= 60, answer-first, clear entities, valid schema → PASS."""
        result = gate4_result(
            citability_score=75,
            answer_first_structure=True,
            entities_clear=True,
            structured_data_valid=True,
        )
        assert result == "PASS"

    def test_gate4_repair_low_citability(self):
        """M1: Citability < 60 → REPAIR."""
        result = gate4_result(
            citability_score=50,
            answer_first_structure=True,
            entities_clear=True,
            structured_data_valid=True,
        )
        assert result == "REPAIR"

    def test_gate4_repair_answer_first(self):
        """M1: No answer-first structure → REPAIR."""
        result = gate4_result(
            citability_score=80,
            answer_first_structure=False,
            entities_clear=True,
            structured_data_valid=True,
        )
        assert result == "REPAIR"

    def test_gate4_repair_entities(self):
        """M1: Entities not clear → REPAIR."""
        result = gate4_result(
            citability_score=80,
            answer_first_structure=True,
            entities_clear=False,
            structured_data_valid=True,
        )
        assert result == "REPAIR"


def _make_uc_draft() -> dict:
    """Build a schema-valid use-case-capability draft for unified_gate tests."""
    return {
        "slug": "google-ads-automation",
        "keyword": "google ads automation",
        "intent": "informational",
        "template_used": "use-case-capability",
        "meta_title": "Google Ads Automation Guide",
        "meta_description": "Automate Google Ads bidding and campaign workflows.",
        "schema_type": "UseCaseCapabilityArticle",
        "structured_data": {
            "h1": "Google Ads Automation Guide",
            "quick_answer": (
                "Google Ads automation helps performance marketers automate bidding "
                "strategies, budget allocation, and campaign optimization workflows "
                "across multiple Google Ads accounts, reducing manual work while "
                "improving return on ad spend."
            ),
            "capabilities": [
                {
                    "title": "Automated Bidding",
                    "description": "Smart bidding strategies that optimize for conversions.",
                }
            ],
            "workflow_steps": [
                {
                    "step_number": 1,
                    "title": "Connect Account",
                    "description": "Link your Google Ads account to the automation platform.",
                }
            ],
            "use_cases": [
                {
                    "title": "E-commerce Scaling",
                    "description": "Automate product listing ads for large catalogs.",
                }
            ],
            "integrations": [
                {
                    "name": "Google Ads API",
                    "description": "Direct API connection for real-time bid management.",
                }
            ],
            "benefits": [
                {
                    "title": "Time Savings",
                    "description": "Reduce manual campaign management time.",
                }
            ],
            "faq": [
                {
                    "question": "What is Google Ads automation?",
                    "answer": "Google Ads automation uses scripts and APIs to manage campaigns programmatically.",
                },
                {
                    "question": "How does automated bidding work?",
                    "answer": "Automated bidding uses machine learning to set competitive bids for each auction.",
                },
                {
                    "question": "Can automation improve ROI?",
                    "answer": "Yes, automation can improve ROI by optimizing bids in real-time.",
                },
            ],
            "related_pages": [],
            "cta": {
                "heading": "Start Automating Today",
                "body": "Connect your Google Ads account and launch your first automated workflow.",
                "button_label": "Get Started",
            },
            "external_citations": [
                {"source": "Google Ads API Documentation", "url": "https://developers.google.com/google-ads/api"}
            ],
            "information_gain": (
                "Practical workflow examples with API integration patterns "
                "not found in competitor guides."
            ),
            "image_specs": [],
            "key_signals": ["Real-time bid adjustments", "Budget pacing alerts"],
        },
    }


def _passing_guardrail_report() -> dict:
    """Pre-computed pSEO Engine guardrail report where all 13 checks pass."""
    check_names = [
        "ai_artifacts",
        "title_uniqueness",
        "differentiation",
        "external_citations",
        "entity_density",
        "word_count",
        "faq_count",
        "keyword_presence",
        "section_completeness",
        "template_required_sections",
        "structural_repetition",
        "information_gain",
        "schema_validation",
    ]
    return {
        "article_slug": "google-ads-automation",
        "blocked": False,
        "warnings": [],
        "results": [
            {
                "check_name": name,
                "passed": True,
                "severity": "blocking" if i < 9 or name in (
                    "template_required_sections", "structural_repetition",
                    "information_gain", "schema_validation",
                ) else "advisory",
                "message": "ok",
            }
            for i, name in enumerate(check_names)
        ],
    }


def _blocking_guardrail_report() -> dict:
    """Pre-computed report where a blocking check fails."""
    report = _passing_guardrail_report()
    report["blocked"] = True
    for r in report["results"]:
        if r["check_name"] == "external_citations":
            r["passed"] = False
            r["message"] = "Missing or empty external_citations field (E-E-A-T requirement)."
    return report


class TestUnifiedGatePSEOGuardrails:
    """Unified gate consumes real pSEO Engine 13-check run_checks() results."""

    def test_all_pseo_guardrails_passing(self):
        """All 13 pSEO guardrails passing → not REJECT, results represented."""
        from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo

        draft = _make_uc_draft()
        draft["guardrail_report"] = _passing_guardrail_report()
        result = validate_pseo(draft, existing_titles=[])

        assert result["decision"] != "REJECT"
        assert result["blocked"] is False
        assert result["gate3"]["blocked"] is False
        assert len(result["gate3"]["guardrail_results"]) == 13
        assert all(r["passed"] for r in result["gate3"]["guardrail_results"])

    def test_blocking_pseo_guardrail_causes_reject(self):
        """A blocking pSEO guardrail failure cannot result in PASS."""
        from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo

        draft = _make_uc_draft()
        draft["guardrail_report"] = _blocking_guardrail_report()
        result = validate_pseo(draft, existing_titles=[])

        assert result["decision"] == "REJECT"
        assert result["blocked"] is True
        assert result["gate3"]["blocked"] is True
        failed = [r for r in result["gate3"]["guardrail_results"] if not r["passed"]]
        assert any(r["severity"] == "blocking" for r in failed)

    def test_aeo_geo_checks_still_evaluated(self):
        """AEO/GEO (GATE 4) and citability checks still run alongside pSEO guardrails."""
        from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo

        draft = _make_uc_draft()
        draft["guardrail_report"] = _passing_guardrail_report()
        result = validate_pseo(draft, existing_titles=[])

        # GATE 4 present with expected keys
        assert "gate4" in result
        for key in (
            "citability_score",
            "answer_first_structure",
            "entities_clear",
            "structured_data_valid",
        ):
            assert key in result["gate4"]

        # Citability checks still evaluated
        assert result["gate3"]["citability_total"] == 4
        assert result["gate3"]["citability_score"] >= 0
        assert result["gate4"]["answer_first_structure"] is True
        assert result["gate4"]["entities_clear"] is True
        assert result["gate4"]["structured_data_valid"] is True

    def test_backward_compatible_result_shape(self):
        """Existing result shape preserved for current consumers."""
        from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo

        draft = _make_uc_draft()
        draft["guardrail_report"] = _passing_guardrail_report()
        result = validate_pseo(draft, existing_titles=[])

        for key in ("decision", "score", "grade", "blocked", "warnings", "gate3", "gate4"):
            assert key in result

        for key in (
            "blocked",
            "warnings",
            "citability_score",
            "citability_grade",
            "citability_passed",
            "citability_total",
            "guardrail_results",
        ):
            assert key in result["gate3"]

        for key in (
            "citability_score",
            "answer_first_structure",
            "entities_clear",
            "structured_data_valid",
        ):
            assert key in result["gate4"]

        assert result["decision"] in ("PASS", "REPAIR", "REJECT")
        assert isinstance(result["score"], int)
        assert isinstance(result["warnings"], list)

    def test_fallback_runs_checks_when_no_precomputed_report(self):
        """Draft without guardrail_report → run_checks() is called and used."""
        from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo

        draft = _make_uc_draft()  # no guardrail_report key
        assert "guardrail_report" not in draft
        # Empty external_citations → blocking failure in real run_checks()
        draft["structured_data"]["external_citations"] = []

        result = validate_pseo(draft, existing_titles=[])

        assert result["decision"] == "REJECT"
        assert result["blocked"] is True
        # Real pSEO Engine check names present (not fabricated placeholders)
        check_names = {r["check_name"] for r in result["gate3"]["guardrail_results"]}
        assert "external_citations" in check_names
        assert "schema_validation" in check_names
        assert "ai_artifacts" in check_names
        assert len(result["gate3"]["guardrail_results"]) == 13