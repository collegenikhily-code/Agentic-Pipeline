"""GATE 4: AEO/GEO Quality checks."""

from __future__ import annotations
from typing import Any, Literal


def gate4_result(
    citability_score: int,
    answer_first_structure: bool,
    entities_clear: bool,
    structured_data_valid: bool,
    egeo_findings: dict | None = None,
) -> Literal["PASS", "REPAIR", "REJECT"]:
    """GATE 4: AEO/GEO readiness decision.
    
    M1: Citability score >= 60, answer-first structure, clear entities, valid schema.
    eGEO findings optional (PARTIALLY VERIFIED).
    """
    if citability_score < 60:
        return "REPAIR"
    
    if not answer_first_structure:
        return "REPAIR"
    
    if not entities_clear:
        return "REPAIR"
    
    if not structured_data_valid:
        return "REPAIR"
    
    # eGEO findings (optional; if available and indicate issues, REPAIR)
    if egeo_findings:
        if egeo_findings.get("critical_issues"):
            return "REPAIR"
    
    return "PASS"