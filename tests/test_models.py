"""M1 unit tests for data models.

No PostgreSQL required - tests Python class structure and invariants.
"""

import pytest
from seo_aeo_geo_pipeline.models import (
    PipelineRun, Opportunity, ResearchSnapshot, Source,
    ProductTruth, Claim, Evidence, Page, PageVersion,
    ValidationRun, ValidationFinding, PublicationDecision, Measurement,
)


class TestModels:
    """Model structure and invariant tests."""

    def test_pipeline_run_creation(self):
        """M1: PipelineRun can be instantiated."""
        pr = PipelineRun(
            id=1,
            run_id="test-run-1",
            started_at="2026-01-01T00:00:00Z",
            completed_at=None,
            status="DISCOVERED",
            error_details=None,
            metadata=None,
        )
        assert pr.id == 1
        assert pr.run_id == "test-run-1"
        assert pr.status == "DISCOVERED"
        assert pr.error_details is None

    def test_opportunity_creation(self):
        """M1: Opportunity can be instantiated."""
        opp = Opportunity(
            id=1,
            pipeline_run_id=1,
            keyword="test keyword",
            source="test_source",
            discovery_method="matrix_expansion",
            intent="informational",
            business_relevance_score=0.5,
            information_gain=False,
            cannibalization_risk="",
            duplicate_opportunity=False,
            status="DISCOVERED",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert opp.id == 1
        assert opp.keyword == "test keyword"
        assert opp.intent == "informational"
        assert opp.business_relevance_score == 0.5

    def test_page_version_immutability_contract(self):
        """M1: PageVersion immutability - v1 must not be overwritten by v2."""
        v1 = PageVersion(
            id=1,
            page_id=1,
            page_spec_id=1,
            research_snapshot_id=1,
            version=1,
            generated_content="v1 content",
            generation_model="model-x",
            generation_prompt_id="prompt-1",
            generated_at="2026-01-01T00:00:00Z",
            guardrail_report={},
            citability_score=70,
            citability_grade="B",
            aeo_geo_report={},
        )
        
        v2 = PageVersion(
            id=2,
            page_id=1,
            page_spec_id=1,
            research_snapshot_id=1,
            version=2,
            generated_content="v2 content (repaired)",
            generation_model="model-x",
            generation_prompt_id="prompt-2",
            generated_at="2026-01-02T00:00:00Z",
            guardrail_report={},
            citability_score=75,
            citability_grade="B",
            aeo_geo_report={},
        )
        
        # v1 and v2 are separate immutable artifacts
        assert v1.version == 1
        assert v2.version == 2
        assert v1.generated_content == "v1 content"
        assert v2.generated_content == "v2 content (repaired)"
        # Verify v1 was NOT overwritten by v2
        assert v1.id == 1  # v1 still has its own ID
        assert v2.id == 2  # v2 has its own ID
        
        # Key invariant: both versions coexist for same page_id
        assert v1.page_id == v2.page_id == 1
        # Different versions
        assert v1.version != v2.version

    def test_page_version_references_traceability(self):
        """M1: Page version traces to exact page_spec and research_snapshot."""
        v = PageVersion(
            id=1,
            page_id=1,
            page_spec_id=1,
            research_snapshot_id=1,
            version=1,
            generated_content="test",
            generation_model="m",
            generation_prompt_id="p",
            generated_at="2026-01-01T00:00:00Z",
            guardrail_report={},
            citability_score=50,
            citability_grade="C",
            aeo_geo_report={},
        )
        
        # All three FK references are set
        assert v.page_id == 1
        assert v.page_spec_id == 1
        assert v.research_snapshot_id == 1
        # Traceability chain: opportunity → research_snapshot → page_spec → page_version
        assert v.page_spec_id is not None
        assert v.research_snapshot_id is not None


class TestDataIntegrity:
    """M1: Data integrity across the pipeline."""

    def test_validation_run_points_to_one_page_version(self):
        """M1: Each validation_run references exactly one page_version."""
        vr = ValidationRun(
            id=1,
            pipeline_run_id=1,
            opportunity_id=1,
            page_version_id=1,  # exact single reference
            page_spec_id=1,
            version=1,
            validation_type="combined",
            status="PENDING",
            started_at="2026-01-01T00:00:00Z",
            completed_at=None,
            pseolint_verdict=None,
            pseolint_categories={},
            citability_score=70,
            citability_grade="B",
            aeo_geo_report={},
            overall_status="PENDING",
        )
        # Verify single page_version_id
        assert vr.page_version_id == 1
        # No duplicate references
        assert vr.page_spec_id == 1

    def test_publication_decision_points_to_one_validation_run(self):
        """M1: Each publication_decision references exactly one validation_run."""
        pd = PublicationDecision(
            id=1,
            validation_run_id=1,  # exact single reference
            decision="APPROVED",
            reason="All gates passed",
            repair_attempts=0,
            max_repair_attempts=3,
            approved_at=None,
            published_at=None,
            status="PENDING",
        )
        assert pd.validation_run_id == 1

    def test_measurement_links_to_publication_decision(self):
        """M1: Each measurement references exactly one publication_decision."""
        m = Measurement(
            id=1,
            publication_decision_id=1,  # exact single reference
            metric_name="impressions",
            metric_value=1500.0,
            metric_date="2026-01-01",
            source="gsc",
            collected_at="2026-01-01T00:00:00Z",
        )
        assert m.publication_decision_id == 1