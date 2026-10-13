"""Pipeline state persistence - M1 only.

Handles state transitions, version enforcement, and FK integrity.
Uses psycopg2 directly (no SQLAlchemy) per the no-paid-tools constraint.
Database integration tests use Docker-based PostgreSQL.

State machine: DISCOVERED → RESEARCHING → QUALIFIED → SPEC_READY → 
GENERATING → VALIDATING → REPAIRING → APPROVED → PUBLISHED

Failure states: REJECTED, NOINDEX, FAILED (explicit, terminal).
"""

from __future__ import annotations
import logging
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from seo_aeo_geo_pipeline.models import (
    PipelineRun, Opportunity, ResearchSnapshot, Source,
    ProductTruth, Claim, Evidence, Page, PageVersion,
    ValidationRun, ValidationFinding, PublicationDecision, Measurement,
)

logger = logging.getLogger(__name__)


# ── State Machine Namespace ────────────────────────────────────────────────

# Valid state transitions: from_state → {to_states}
# PUBLISHED and all Failure states are TERMINAL - no outgoing transitions
TRANSITIONS = {
    "DISCOVERED": {"RESEARCHING", "REJECTED"},
    "RESEARCHING": {"QUALIFIED", "REJECTED"},
    "QUALIFIED": {"SPEC_READY", "REJECTED", "NOINDEX", "FAILED"},
    "SPEC_READY": {"GENERATING", "REJECTED"},
    "GENERATING": {"VALIDATING", "REPAIRING", "REJECTED"},
    "VALIDATING": {"REPAIRING", "APPROVED", "REJECTED"},
    "REPAIRING": {"VALIDATING", "REJECTED"},
    "APPROVED": {"PUBLISHED"},
    "PUBLISHED": set(),  # TERMINAL - no outgoing transitions
    "REJECTED": set(),  # TERMINAL
    "NOINDEX": set(),   # TERMINAL
    "FAILED": set(),    # TERMINAL
}


def can_transition(from_state: str, to_state: str) -> bool:
    """Check if a state transition is valid."""
    allowed = TRANSITIONS.get(from_state, set())
    return to_state in allowed


def transition_allowed(from_state: str, to_state: str) -> bool:
    """Check transition and raise if not allowed."""
    if can_transition(from_state, to_state):
        return True
    raise ValueError(
        f"Invalid state transition: {from_state} → {to_state}. "
        f"Allowed: {TRANSITIONS.get(from_state, 'none')}"
    )


# ── Failure States ─────────────────────────────────────────────────────────

FAILURE_STATES = {"REJECTED", "NOINDEX", "FAILED"}


# ── State Repository ───────────────────────────────────────────────────────

class StateRepository:
    """Persistence layer for pipeline state using psycopg2."""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or "postgresql://postgres@localhost:5432/seo_aeo_geo"

    def _connect(self):
        """Get a database connection."""
        return psycopg2.connect(self.db_url)

    # Pipeline run methods
    def create_pipeline_run(self, run_id: str, status: str = "DISCOVERED") -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pipeline_runs (run_id, status) VALUES (%s, %s) RETURNING id, run_id, started_at, status",
                    (run_id, status),
                )
                row = cur.fetchone()
                conn.commit()
                return {"id": row[0], "run_id": row[1], "started_at": row[2], "status": row[3]}
        finally:
            conn.close()

    def update_pipeline_run(self, run_id: str, status: str, error_details: Optional[dict] = None) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pipeline_runs SET status = %s, error_details = %s, completed_at = NOW() WHERE run_id = %s",
                    (status, error_details, run_id),
                )
                conn.commit()
        finally:
            conn.close()

    # Opportunity methods
    def create_opportunity(self, pipeline_run_id: int, keyword: str, **kwargs) -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO opportunities (pipeline_run_id, keyword, source, discovery_method, intent, "
                    "business_relevance_score, information_gain, cannibalization_risk, duplicate_opportunity, "
                    "status, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()) RETURNING *",
                    (pipeline_run_id, keyword, kwargs.get("source"), kwargs.get("discovery_method"),
                     kwargs.get("intent"), kwargs.get("business_relevance_score", 0.0),
                     kwargs.get("information_gain", False), kwargs.get("cannibalization_risk", ""),
                     kwargs.get("duplicate_opportunity", False), "DISCOVERED"),
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else {}
        finally:
            conn.close()

    # Research snapshot methods
    def create_research_snapshot(self, opportunity_id: int, data_hash: str, provider: str = "manual", **kwargs) -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO research_snapshots (opportunity_id, created_at, status, source_count, data_hash, provider) "
                    "VALUES (%s, NOW(), 'ACTIVE', %s, %s, %s) RETURNING *",
                    (opportunity_id, len(kwargs.get("sources", [])), data_hash, provider),
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else {}
        finally:
            conn.close()

    # Page version methods - immutability
    def create_page_version(self, page_id: int, page_spec_id: int, research_snapshot_id: int,
                           version: int, generated_content: str, **kwargs) -> dict:
        """CREATE only - UPDATE/DELETE not part of normal application behavior."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO page_versions (page_id, page_spec_id, research_snapshot_id, version, "
                    "generated_content, generation_model, generation_prompt_id, generated_at, "
                    "guardrail_report, citability_score, citability_grade, aeo_geo_report) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s) RETURNING *",
                    (page_id, page_spec_id, research_snapshot_id, version,
                     generated_content, kwargs.get("generation_model"), kwargs.get("generation_prompt_id"),
                     kwargs.get("guardrail_report"), kwargs.get("citability_score", 0),
                     kwargs.get("citability_grade", "D"), kwargs.get("aeo_geo_report")),
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else {}
        finally:
            conn.close()

    def get_page_version(self, version_id: int) -> Optional[dict]:
        """READ only - retrieve a page version."""
        conn = self._connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM page_versions WHERE id = %s", (version_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    # Validation run methods
    def create_validation_run(self, pipeline_run_id: int, opportunity_id: int,
                              page_version_id: int, page_spec_id: int,
                              validation_type: str = "combined") -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO validation_runs (pipeline_run_id, opportunity_id, page_version_id, "
                    "page_spec_id, validation_type, status) "
                    "VALUES (%s, %s, %s, %s, %s, 'PENDING') RETURNING *",
                    (pipeline_run_id, opportunity_id, page_version_id, page_spec_id, validation_type),
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else {}
        finally:
            conn.close()

    def update_validation_run(self, run_id: int, status: str, overall_status: str,
                              pseolint_verdict: str | None = None,
                              pseolint_categories: dict | None = None,
                              citability_score: int | None = None,
                              citability_grade: str | None = None,
                              aeo_geo_report: dict | None = None,
                              overall_status_override: str | None = None) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                sets = ["status = %s, overall_status = %s"]
                vals = [status, overall_status]

                if pseolint_verdict is not None:
                    sets.append("pseolint_verdict = %s")
                    vals.append(pseolint_verdict)
                if pseolint_categories is not None:
                    sets.append("pseolint_categories = %s")
                    vals.append(pseolint_categories)
                if citability_score is not None:
                    sets.append("citability_score = %s")
                    vals.append(citability_score)
                if citability_grade is not None:
                    sets.append("citability_grade = %s")
                    vals.append(citability_grade)
                if aeo_geo_report is not None:
                    sets.append("aeo_geo_report = %s")
                    vals.append(aeo_geo_report)
                if overall_status_override is not None:
                    sets.append("overall_status = %s")
                    vals.append(overall_status_override)

                vals.append(run_id)
                q = f"UPDATE validation_runs SET {', '.join(sets)} WHERE id = %s"
                cur.execute(q, vals)
                conn.commit()
        finally:
            conn.close()

    # Publication decision methods
    def create_publication_decision(self, validation_run_id: int, decision: str,
                                     reason: str, repair_attempts: int = 0,
                                     max_repair_attempts: int = 3) -> dict:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO publication_decisions (validation_run_id, decision, reason, "
                    "repair_attempts, max_repair_attempts, status) "
                    "VALUES (%s, %s, %s, %s, %s, 'PENDING') RETURNING *",
                    (validation_run_id, decision, reason, repair_attempts, max_repair_attempts),
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else {}
        finally:
            conn.close()

    # Immutability enforcement
    def update_page_version(self, *args, **kwargs):
        """UPDATE not allowed on page_versions - application level immutability."""
        raise PermissionError("UPDATE on page_versions not allowed - repair creates new version")

    def delete_page_version(self, *args, **kwargs):
        """DELETE not allowed on page_versions - application level immutability."""
        raise PermissionError("DELETE on page_versions not allowed - repair creates new version")


# ── Module-level exports for convenience ─────────────────────────────────────

# StateMachine is a namespace for transition functions
class StateMachine:
    """Namespace for pipeline state transition logic."""
    TRANSITIONS = TRANSITIONS
    can_transition = can_transition
    transition_allowed = transition_allowed
    FAILURE_STATES = FAILURE_STATES


# Convenience aliases
can_transition = can_transition
transition_allowed = transition_allowed