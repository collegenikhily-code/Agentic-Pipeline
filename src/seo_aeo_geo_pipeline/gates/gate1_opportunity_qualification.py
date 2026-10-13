"""GATE 1-4 definitions for SEO + AEO + GEO content pipeline.

M1: Gate skeleton with check functions and state transition logic.
Full gate implementation (PASS/REPAIR/REJECT outputs) in M2+.
"""

from __future__ import annotations

from typing import Any, Literal


# ── GATE 1: Opportunity Qualification ────────────────────────────────────

def qualify_opportunity(
    keyword: str,
    intent: str,
    business_relevance: float,
    existing_pages: list[str],
    product_truth_refs: list[str],
) -> Literal["QUALIFIED", "REJECTED"]:
    """GATE 1: Check relevance, intent, business relevance, information gain, cannibalization.
    
    M1: Simple eligibility check. Full gate with information gain, cannibalization 
    detection in M2+.
    """
    # M1: Basic qualification - if keyword has intent and business relevance, qualify
    if not keyword or not intent:
        return "REJECTED"
    
    if business_relevance < 0.3:
        return "REJECTED"
    
    # Check for cannibalization against existing pages
    keyword_lower = keyword.lower()
    for existing in existing_pages:
        if keyword_lower in existing.lower():
            return "REJECTED"  # cannibalization risk
    
    return "QUALIFIED"


# ── GATE 2: Evidence + Page Specification ────────────────────────────────

def spec_ready(
    evidence_count: int,
    product_truth_aligned: bool,
    page_type: str,
    required_sections: dict,
    entities: list[str],
    questions: list[str],
    differentiation: str,
) -> Literal["READY", "REJECTED"]:
    """GATE 2: Check sufficient evidence, product truth, page type, sections, entities, questions, differentiation.
    
    M1: Basic checks. Full gate with all requirements in M2+.
    """
    if evidence_count < 1:
        return "REJECTED"
    
    if not product_truth_aligned:
        return "REJECTED"
    
    if page_type not in ("comparison-guide", "product-how-to", "faq-page", "article"):
        return "REJECTED"
    
    if not required_sections:
        return "REJECTED"
    
    if not entities:
        return "REJECTED"
    
    if not questions:
        return "REJECTED"
    
    if not differentiation or differentiation.strip() == "":
        return "REJECTED"
    
    return "READY"


# ── GATE 3: pSEO Integrity / Content Quality ─────────────────────────────

def validate_content_quality(
    guardrail_report: dict,
    citability_report: dict,
) -> Literal["PASS", "REPAIR", "REJECT"]:
    """GATE 3: Run guardrails + citability checks.
    
    M1: Basic pass/fail logic. Full REPAIR loop with versioning M2+.
    """
    blocked = guardrail_report.get("blocked", False)
    citability_score = citability_report.get("score", 0)
    
    if blocked:
        return "REJECT"
    
    if citability_score < 50:
        return "REPAIR"
    
    return "PASS"


# ── GATE 4: AEO/GEO Quality ────────────────────────────────────────────

def validate_aeo_geo(
    citability_score: int,
    answer_first: bool,
    entities_clear: bool,
    structured_data_valid: bool,
) -> Literal["PASS", "REPAIR", "REJECT"]:
    """GATE 4: AEO/GEO readiness check.
    
    M1: Basic citability + structure checks. Full eGEO integration M2+.
    """
    if citability_score < 60:
        return "REPAIR"
    
    if not answer_first:
        return "REPAIR"
    
    if not entities_clear:
        return "REPAIR"
    
    if not structured_data_valid:
        return "REPAIR"
    
    return "PASS"