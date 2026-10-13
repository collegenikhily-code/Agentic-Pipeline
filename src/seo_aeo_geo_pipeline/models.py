"""SQL model definitions for M1 schema.

These definitions match the corrected PostgreSQL schema from the migration files.
They are used for test fixtures and ORM-like operations without SQLAlchemy.
"""

from datetime import datetime, timezone
from typing import Any, Optional


class PipelineRun:
    """Represents a pipeline execution run."""
    
    def __init__(
        self,
        id: int,
        run_id: str,
        started_at: datetime,
        completed_at: Optional[datetime],
        status: str,
        error_details: Optional[dict],
        metadata: Optional[dict],
    ):
        self.id = id
        self.run_id = run_id
        self.started_at = started_at
        self.completed_at = completed_at
        self.status = status
        self.error_details = error_details
        self.metadata = metadata


class Opportunity:
    """Represents a content opportunity."""
    
    def __init__(
        self,
        id: int,
        pipeline_run_id: int,
        keyword: str,
        source: str,
        discovery_method: str,
        intent: str,
        business_relevance_score: float,
        information_gain: bool,
        cannibalization_risk: str,
        duplicate_opportunity: bool,
        status: str,
        created_at: datetime,
        updated_at: datetime,
    ):
        self.id = id
        self.pipeline_run_id = pipeline_run_id
        self.keyword = keyword
        self.source = source
        self.discovery_method = discovery_method
        self.intent = intent
        self.business_relevance_score = business_relevance_score
        self.information_gain = information_gain
        self.cannibalization_risk = cannibalization_risk
        self.duplicate_opportunity = duplicate_opportunity
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at


class ResearchSnapshot:
    """Normalized research dataset snapshot."""
    
    def __init__(
        self,
        id: int,
        opportunity_id: int,
        created_at: datetime,
        status: str,
        source_count: int,
        data_hash: str,
        provider: str,
        metadata: Optional[dict],
    ):
        self.id = id
        self.opportunity_id = opportunity_id
        self.created_at = created_at
        self.status = status
        self.source_count = source_count
        self.data_hash = data_hash
        self.provider = provider
        self.metadata = metadata


class Source:
    """Individual research source within a snapshot."""
    
    def __init__(
        self,
        id: int,
        research_snapshot_id: int,
        source_url: str,
        source_type: str,
        source_date: str,
        excerpt: str,
        confidence: float,
        verification_status: str,
        collector: str,
    ):
        self.id = id
        self.research_snapshot_id = research_snapshot_id
        self.source_url = source_url
        self.source_type = source_type
        self.source_date = source_date
        self.excerpt = excerpt
        self.confidence = confidence
        self.verification_status = verification_status
        self.collector = collector


class ProductTruth:
    """Authoritative product/company facts."""
    
    def __init__(
        self,
        id: int,
        product_id: str,
        feature_name: str,
        feature_description: str,
        pricing_info: str,
        customer_type: str,
        statistic_source: str,
        confidence: float,
        verification_status: str,
        last_verified_at: Optional[datetime],
        source_url: str,
    ):
        self.id = id
        self.product_id = product_id
        self.feature_name = feature_name
        self.feature_description = feature_description
        self.pricing_info = pricing_info
        self.customer_type = customer_type
        self.statistic_source = statistic_source
        self.confidence = confidence
        self.verification_status = verification_status
        self.last_verified_at = last_verified_at
        self.source_url = source_url


class Claim:
    """A claim traced to product truth or evidence."""
    
    def __init__(
        self,
        id: int,
        product_truth_id: int,
        claim_text: str,
        claim_id_uuid: str,
        claim_type: str,
        confidence: float,
        verification_status: str,
        source_trace: dict,
        created_at: datetime,
    ):
        self.id = id
        self.product_truth_id = product_truth_id
        self.claim_text = claim_text
        self.claim_id_uuid = claim_id_uuid
        self.claim_type = claim_type
        self.confidence = confidence
        self.verification_status = verification_status
        self.source_trace = source_trace
        self.created_at = created_at


class Evidence:
    """Evidence supporting a claim."""
    
    def __init__(
        self,
        id: int,
        claim_id: int,
        source_id: int,
        evidence_excerpt: str,
        confidence: float,
        verification_status: str,
        page_location: str,
        product_truth_status: str,
        version: int,
    ):
        self.id = id
        self.claim_id = claim_id
        self.source_id = source_id
        self.evidence_excerpt = evidence_excerpt
        self.confidence = confidence
        self.verification_status = verification_status
        self.page_location = page_location
        self.product_truth_status = product_truth_status
        self.version = version


class PageSpec:
    """Page specification template."""
    
    def __init__(
        self,
        id: int,
        opportunity_id: int,
        version: int,
        page_type: str,
        title_tag: str,
        meta_description: str,
        required_sections: dict,
        entity_data: dict,
        questions: list,
        differentiation_strategy: str,
        internal_linking_plan: dict,
        schema_requirements: dict,
        status: str,
        research_snapshot_id: int,
        created_at: datetime,
    ):
        self.id = id
        self.opportunity_id = opportunity_id
        self.version = version
        self.page_type = page_type
        self.title_tag = title_tag
        self.meta_description = meta_description
        self.required_sections = required_sections
        self.entity_data = entity_data
        self.questions = questions
        self.differentiation_strategy = differentiation_strategy
        self.internal_linking_plan = internal_linking_plan
        self.schema_requirements = schema_requirements
        self.status = status
        self.research_snapshot_id = research_snapshot_id
        self.created_at = created_at


class Page:
    """Logical page entity."""
    
    def __init__(
        self,
        id: int,
        page_spec_id: int,
        current_page_version_id: Optional[int],
        content_path: str,
        generation_status: str,
        created_at: datetime,
    ):
        self.id = id
        self.page_spec_id = page_spec_id
        self.current_page_version_id = current_page_version_id
        self.content_path = content_path
        self.generation_status = generation_status
        self.created_at = created_at


class PageVersion:
    """Immutable page artifact version."""
    
    def __init__(
        self,
        id: int,
        page_id: int,
        page_spec_id: int,
        research_snapshot_id: int,
        version: int,
        generated_content: str,
        generation_model: str,
        generation_prompt_id: str,
        generated_at: datetime,
        guardrail_report: dict,
        citability_score: int,
        citability_grade: str,
        aeo_geo_report: dict,
    ):
        self.id = id
        self.page_id = page_id
        self.page_spec_id = page_spec_id
        self.research_snapshot_id = research_snapshot_id
        self.version = version
        self.generated_content = generated_content
        self.generation_model = generation_model
        self.generation_prompt_id = generation_prompt_id
        self.generated_at = generated_at
        self.guardrail_report = guardrail_report
        self.citability_score = citability_score
        self.citability_grade = citability_grade
        self.aeo_geo_report = aeo_geo_report


class ValidationRun:
    """Validation execution for a page version."""
    
    def __init__(
        self,
        id: int,
        pipeline_run_id: int,
        opportunity_id: int,
        page_version_id: int,
        page_spec_id: int,
        version: int,
        validation_type: str,
        status: str,
        started_at: datetime,
        completed_at: Optional[datetime],
        pseolint_verdict: str,
        pseolint_categories: dict,
        citability_score: int,
        citability_grade: str,
        aeo_geo_report: dict,
        overall_status: str,
    ):
        self.id = id
        self.pipeline_run_id = pipeline_run_id
        self.opportunity_id = opportunity_id
        self.page_version_id = page_version_id
        self.page_spec_id = page_spec_id
        self.version = version
        self.validation_type = validation_type
        self.status = status
        self.started_at = started_at
        self.completed_at = completed_at
        self.pseolint_verdict = pseolint_verdict
        self.pseolint_categories = pseolint_categories
        self.citability_score = citability_score
        self.citability_grade = citability_grade
        self.aeo_geo_report = aeo_geo_report
        self.overall_status = overall_status


class ValidationFinding:
    """Individual finding from a validation run."""
    
    def __init__(
        self,
        id: int,
        validation_run_id: int,
        finding_type: str,
        rule_name: str,
        passed: bool,
        severity: str,
        message: str,
        remediation: str,
        page_version: int,
    ):
        self.id = id
        self.validation_run_id = validation_run_id
        self.finding_type = finding_type
        self.rule_name = rule_name
        self.passed = passed
        self.severity = severity
        self.message = message
        self.remediation = remediation
        self.page_version = page_version


class PublicationDecision:
    """Final publication decision."""
    
    def __init__(
        self,
        id: int,
        validation_run_id: int,
        decision: str,
        reason: str,
        repair_attempts: int,
        max_repair_attempts: int,
        approved_at: Optional[datetime],
        published_at: Optional[datetime],
        status: str,
    ):
        self.id = id
        self.validation_run_id = validation_run_id
        self.decision = decision
        self.reason = reason
        self.repair_attempts = repair_attempts
        self.max_repair_attempts = max_repair_attempts
        self.approved_at = approved_at
        self.published_at = published_at
        self.status = status


class Measurement:
    """Published page measurement data."""
    
    def __init__(
        self,
        id: int,
        publication_decision_id: int,
        metric_name: str,
        metric_value: float,
        metric_date: str,
        source: str,
        collected_at: datetime,
    ):
        self.id = id
        self.publication_decision_id = publication_decision_id
        self.metric_name = metric_name
        self.metric_value = metric_value
        self.metric_date = metric_date
        self.source = source
        self.collected_at = collected_at


# ── PageJob: Minimal CATALYST contract ────────────────────────────────────

# Valid PageJob status transitions
PAGEJOB_TRANSITIONS = {
    "QUEUED": {"RESEARCHING", "FAILED"},
    "RESEARCHING": {"RESEARCHED", "FAILED"},
    "RESEARCHED": {"COMPLETED", "FAILED"},
    "COMPLETED": set(),   # terminal
    "FAILED": {"QUEUED"},  # retry: back to QUEUED
}

PAGEJOB_FAILURE_STATES = {"FAILED"}


def pagejob_can_transition(from_status: str, to_status: str) -> bool:
    """Check if a PageJob status transition is valid."""
    allowed = PAGEJOB_TRANSITIONS.get(from_status, set())
    return to_status in allowed


class PageJob:
    """Minimal PageJob model for CATALYST orchestrator.

    Lifecycle: QUEUED → RESEARCHING → RESEARCHED → COMPLETED
                                     ↘ FAILED (retryable: back to QUEUED)
    """

    def __init__(
        self,
        job_id: str,
        keyword: str,
        intent: str = "informational",
        status: str = "QUEUED",
        research_result: Optional[dict] = None,
        error: Optional[str] = None,
        retry_count: int = 0,
        max_retries: int = 2,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.job_id = job_id
        self.keyword = keyword
        self.intent = intent
        self.status = status
        self.research_result = research_result
        self.error = error
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

    def transition(self, to_status: str) -> None:
        """Transition to a new status, raising ValueError if invalid."""
        if not pagejob_can_transition(self.status, to_status):
            raise ValueError(
                f"Invalid PageJob transition: {self.status} → {to_status}. "
                f"Allowed: {PAGEJOB_TRANSITIONS.get(self.status, 'none')}"
            )
        self.status = to_status
        self.updated_at = datetime.now(timezone.utc)

    def mark_researching(self) -> None:
        self.transition("RESEARCHING")

    def mark_researched(self, research_result: dict) -> None:
        self.research_result = research_result
        self.transition("RESEARCHED")

    def mark_completed(self) -> None:
        self.transition("COMPLETED")

    def mark_failed(self, error: str) -> None:
        self.error = error
        self.transition("FAILED")

    def can_retry(self) -> bool:
        """Check if this job can be retried."""
        return self.status == "FAILED" and self.retry_count < self.max_retries

    def retry(self) -> None:
        """Reset to QUEUED for retry, incrementing retry_count."""
        if not self.can_retry():
            raise ValueError(
                f"Cannot retry: status={self.status}, retries={self.retry_count}/{self.max_retries}"
            )
        self.retry_count += 1
        self.error = None
        self.transition("QUEUED")

    def is_terminal(self) -> bool:
        """Check if this job is in a terminal state."""
        return self.status in ("COMPLETED",) or (
            self.status == "FAILED" and not self.can_retry()
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "job_id": self.job_id,
            "keyword": self.keyword,
            "intent": self.intent,
            "status": self.status,
            "research_result": self.research_result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }