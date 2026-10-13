"""GATE 2: Evidence + Page Specification checks."""

from __future__ import annotations
from typing import Any, Literal


def check_evidence_sufficient(
    evidence_count: int,
    min_evidence: int = 1,
) -> bool:
    """Check if enough reliable evidence exists."""
    return evidence_count >= min_evidence


def check_product_truth_aligned(
    claims: list[dict],
    product_truth_db: dict,
) -> bool:
    """Check all important claims are supported by product truth."""
    if not claims:
        return False
    
    for claim in claims:
        claim_text = claim.get("text", "").lower()
        # Check if claim traces to product truth
        found = False
        for pt_key, pt_value in product_truth_db.items():
            if claim_text in str(pt_value).lower():
                found = True
                break
        if not found:
            return False
    
    return True


def check_page_type(
    page_type: str,
    valid_types: list[str],
) -> bool:
    """Check page type is valid."""
    return page_type in valid_types


def check_required_sections(
    required_sections: dict,
    min_sections: int = 1,
) -> bool:
    """Check required sections are defined."""
    return len(required_sections) >= min_sections


def check_entities_identified(
    entities: list[str],
    min_entities: int = 1,
) -> bool:
    """Check entities are identified."""
    return len(entities) >= min_entities


def check_questions_identified(
    questions: list[str],
    min_questions: int = 1,
) -> bool:
    """Check questions are identified."""
    return len(questions) >= min_questions


def check_differentiation_defined(
    differentiation: str,
) -> bool:
    """Check differentiation strategy is defined."""
    return differentiation is not None and differentiation.strip() != ""


def check_research_complete(
    snapshot: dict,
) -> bool:
    """Check if research is complete and eligible for pSEO generation.

    Only snapshots with completion_status == "complete" pass.
    Missing/unknown status is treated as NOT complete (safe default).
    """
    return snapshot.get("completion_status") == "complete"