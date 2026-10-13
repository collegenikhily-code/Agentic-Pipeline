"""Unified validation gate combining GATE 3 (pSEO integrity), GATE 4 (AEO/GEO readiness), and Technical SEO."""

from __future__ import annotations

from typing import Any, Literal

from seo_aeo_geo_pipeline.gates.gate3_pseo_quality import (
    evaluate_citability,
    gate3_result as gate3_result_func,
)
from seo_aeo_geo_pipeline.gates.gate4_aeo_geo import gate4_result as gate4_result_func
from seo_aeo_geo_pipeline.gates.technical_seo import evaluate_technical_seo


def _get_pseo_guardrail_report(
    draft: dict,
    existing_titles: list[str],
    corpus_texts: list[str],
) -> dict[str, Any]:
    """Return the pSEO Engine 13-check guardrail report for a draft.

    Prefers the report already computed by pSEO Engine generate_article()
    via run_checks() and stored on the draft as ``guardrail_report``.
    Falls back to running run_checks() directly for drafts that do not
    carry a pre-computed report (e.g. hand-built test fixtures).

    The flat-dict mapping matches the canonical pattern in
    pseo/generate.py and pseo/eval/report.py: run_checks() expects
    content fields at the top level plus slug/keyword/template.
    """
    report = draft.get("guardrail_report")
    if report is not None:
        if hasattr(report, "model_dump"):
            report = report.model_dump()
        if isinstance(report, dict) and isinstance(report.get("results"), list):
            return report

    from pseo.guardrails import run_checks

    structured_data = draft.get("structured_data", {})
    guardrails_input = {
        **structured_data,
        "slug": draft.get("slug", "unknown"),
        "keyword": draft.get("keyword", ""),
        "template": draft.get("template") or draft.get("template_used", ""),
    }
    result = run_checks(
        guardrails_input,
        existing_titles=existing_titles,
        corpus_texts=corpus_texts,
    )
    return result.model_dump()


def validate_pseo(
    draft: dict,
    existing_titles: list[str] | None = None,
    egeo_findings: dict | None = None,
    html: str | None = None,
    artifact: dict | None = None,
    research_snapshot: dict | None = None,
) -> dict[str, Any]:
    """Run full GATE 3 + GATE 4 + Technical SEO validation on a generated draft.

    GATE 3 uses the real pSEO Engine 13-check run_checks() report
    (9 blocking + 4 advisory) as the authoritative integrity input,
    combined with citability scoring. GATE 4 covers AEO/GEO readiness
    (citability >= 60, answer-first structure, clear entities, valid schema).
    Technical SEO (optional, when html provided) checks the rendered page.
    Research completeness (optional) checks if research phase was complete.

    Args:
        draft: Draft article dict from pSEO Engine generate_article().
               May carry a pre-computed ``guardrail_report`` from run_checks().
        existing_titles: List of existing H1/titles for uniqueness check
        egeo_findings: Optional eGEO findings dict with critical_issues key
        html: Optional rendered HTML for technical SEO gate
        artifact: Optional artifact metadata for technical SEO gate
        research_snapshot: Optional research snapshot with completion_status

    Returns:
        dict with keys:
        - decision: "PASS" | "REPAIR" | "REJECT"
        - score: int (citability score 0-100)
        - grade: str ("A".."D")
        - blocked: bool (any blocking failure across all gates)
        - warnings: list[str]
        - gate3: dict with pSEO guardrail + citability details
        - gate4: dict with AEO/GEO check details
        - technical_seo: dict with technical SEO check details (when html provided)
        - research_completeness: dict with research status (when research_snapshot provided)
    """
    # --- Research Completeness Check ---
    research_completeness = {"status": "unknown", "blocked": False, "warnings": []}
    if research_snapshot is not None:
        completion_status = research_snapshot.get("completion_status", "unknown")
        if completion_status == "complete":
            research_completeness = {"status": "complete", "blocked": False, "warnings": []}
        elif completion_status.startswith("partial_"):
            # Partial research is a blocking issue for PASS
            research_completeness = {
                "status": completion_status,
                "blocked": True,
                "warnings": [f"Research incomplete: {completion_status}"]
            }
        else:
            research_completeness = {
                "status": completion_status,
                "blocked": True,
                "warnings": [f"Unknown research status: {completion_status}"]
            }

    # --- GATE 3: pSEO Integrity (real pSEO Engine 13-check guardrails) ---
    structured_data = draft.get("structured_data", {})
    guardrail_report = _get_pseo_guardrail_report(
        draft,
        existing_titles or [],
        [],  # corpus_texts not available in M1
    )
    citability_report = evaluate_citability(structured_data)

    gate3_decision = gate3_result_func(guardrail_report, citability_report)

    gate3_summary = {
        "blocked": guardrail_report.get("blocked", False),
        "warnings": guardrail_report.get("warnings", []),
        "citability_score": citability_report.get("score", 0),
        "citability_grade": citability_report.get("grade", "D"),
        "citability_passed": citability_report.get("passed", 0),
        "citability_total": citability_report.get("total", 4),
        "guardrail_results": guardrail_report.get("results", []),
    }

    # --- GATE 4: AEO/GEO Readiness ---
    citability_score = citability_report.get("score", 0)

    # Extract GATE 4 inputs from draft and structured data
    structured_data = draft.get("structured_data", {})

    answer_first_structure = _has_answer_first_structure(structured_data)
    entities_clear = _entities_clear(structured_data)
    structured_data_valid = _structured_data_valid(structured_data)

    gate4_decision = gate4_result_func(
        citability_score=citability_score,
        answer_first_structure=answer_first_structure,
        entities_clear=entities_clear,
        structured_data_valid=structured_data_valid,
        egeo_findings=egeo_findings,
    )

    gate4_summary = {
        "citability_score": citability_score,
        "answer_first_structure": answer_first_structure,
        "entities_clear": entities_clear,
        "structured_data_valid": structured_data_valid,
        "egeo_critical_issues": egeo_findings.get("critical_issues") if egeo_findings else None,
    }

    # --- Component structural validation (use-case-capability pages) ---
    component_warnings = _validate_component_structure(structured_data)
    gate3_summary["warnings"].extend(component_warnings)

    # --- Technical SEO gate (optional, on rendered HTML + artifact) ---
    technical_summary = None
    technical_blocked = False
    technical_decision = None
    if html is not None:
        technical_summary = evaluate_technical_seo(html, artifact)
        technical_blocked = technical_summary.get("blocked", False)
        technical_decision = technical_summary.get("decision")
        gate3_summary["warnings"].extend(technical_summary.get("warnings", []))

    # --- Final Decision ---
    # Priority: REJECT (any blocking across gates) > REPAIR > PASS
    # Technical SEO advisory warnings do NOT escalate to REPAIR;
    # only technical_blocked (blocking failures) can reject.
    # Research completeness blocking issues also cause REJECT.
    blocked = gate3_summary["blocked"] or technical_blocked or research_completeness["blocked"]

    if blocked:
        decision = "REJECT"
    elif gate3_decision == "REPAIR" or gate4_decision == "REPAIR":
        decision = "REPAIR"
    else:
        decision = "PASS"

    result = {
        "decision": decision,
        "score": citability_score,
        "grade": citability_report.get("grade", "D"),
        "blocked": blocked,
        "warnings": list(
            set(gate3_summary["warnings"] + gate4_summary.get("warnings", []) + research_completeness.get("warnings", []))
        ),
        "gate3": gate3_summary,
        "gate4": gate4_summary,
        "research_completeness": research_completeness,
    }
    if technical_summary is not None:
        result["technical_seo"] = technical_summary
    return result


def _has_answer_first_structure(structured_data: dict) -> bool:
    """Check if draft has answer-first structure (quick answer/lead near top)."""
    # Check multiple lead-answer fields used by different template types
    lead_answer = (
        structured_data.get("quick_answer")
        or structured_data.get("answer")
        or structured_data.get("introduction")
        or structured_data.get("opening_thesis")
        or structured_data.get("hook")
        or ""
    )
    if not lead_answer:
        return False
    # Answer-first: lead answer should be present and substantial
    lead_words = len(lead_answer.split())
    return lead_words >= 20


def _entities_clear(structured_data: dict) -> bool:
    """Check if entities are clear and well-represented in structured data."""
    entity_phrases = structured_data.get("entities", [])
    if not isinstance(entity_phrases, list) or not entity_phrases:
        # Try extracting capitalized multi-word phrases from H1
        text = structured_data.get("h1", "") or structured_data.get("title", "")
        if not text:
            return False
        # Check for capitalized words in H1 as entity proxy
        words = text.split()
        entity_phrases = [w for w in words if w[0].isupper() and len(w) > 2]
        # Also check for multi-word capitalized phrases
        for i in range(len(words) - 1):
            if words[i][0].isupper() and words[i+1][0].isupper():
                entity_phrases.append(f"{words[i]} {words[i+1]}")
    return len(entity_phrases) >= 2


def _structured_data_valid(structured_data: dict) -> bool:
    """Check if required structured data fields are present and valid."""
    # Check for H1 (universal requirement)
    if not structured_data.get("h1"):
        return False
    # Check for at least one lead content field
    lead_fields = ["quick_answer", "answer", "introduction", "opening_thesis", "hook"]
    has_lead = any(structured_data.get(f) for f in lead_fields)
    if not has_lead:
        return False
    return True


# ── Component structural validation ────────────────────────────────────────

_PLACEHOLDER_PATTERNS = [
    "option a", "option b", "option c",
    "espresso", "textile", "demo",
    "lorem ipsum", "placeholder", "sample data",
]


def _validate_component_structure(structured_data: dict) -> list[str]:
    """Validate component structure for typed-component page types.

    Checks:
    - Required components exist (quick_answer, faq, cta for use-case-capability)
    - Component schemas are valid (lists are actually lists, dicts have keys)
    - No empty components
    - No placeholder/demo content
    - Entities are present
    """
    warnings: list[str] = []

    # Detect if this is a use-case-capability page (has capabilities field)
    is_uc = "capabilities" in structured_data or "workflow_steps" in structured_data

    if not is_uc:
        return warnings

    # Required components for use-case-capability
    required_components = ["quick_answer", "capabilities", "faq", "cta"]
    for field_name in required_components:
        value = structured_data.get(field_name)
        if not value:
            warnings.append(f"MISSING_COMPONENT: '{field_name}' is empty or absent")

    # Validate capabilities list
    capabilities = structured_data.get("capabilities", [])
    if isinstance(capabilities, list):
        for i, cap in enumerate(capabilities):
            if not isinstance(cap, dict):
                warnings.append(f"INVALID_COMPONENT: capabilities[{i}] is not a dict")
                continue
            if not cap.get("title"):
                warnings.append(f"EMPTY_FIELD: capabilities[{i}].title is empty")
            if not cap.get("description"):
                warnings.append(f"EMPTY_FIELD: capabilities[{i}].description is empty")

    # Validate workflow_steps list
    steps = structured_data.get("workflow_steps", [])
    if isinstance(steps, list):
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                warnings.append(f"INVALID_COMPONENT: workflow_steps[{i}] is not a dict")
                continue
            if not step.get("title"):
                warnings.append(f"EMPTY_FIELD: workflow_steps[{i}].title is empty")

    # Validate use_cases list
    use_cases = structured_data.get("use_cases", [])
    if isinstance(use_cases, list):
        for i, uc in enumerate(use_cases):
            if not isinstance(uc, dict):
                warnings.append(f"INVALID_COMPONENT: use_cases[{i}] is not a dict")
                continue
            if not uc.get("title"):
                warnings.append(f"EMPTY_FIELD: use_cases[{i}].title is empty")

    # Validate integrations list
    integrations = structured_data.get("integrations", [])
    if isinstance(integrations, list):
        for i, integration in enumerate(integrations):
            if not isinstance(integration, dict):
                warnings.append(f"INVALID_COMPONENT: integrations[{i}] is not a dict")
                continue
            if not integration.get("name"):
                warnings.append(f"EMPTY_FIELD: integrations[{i}].name is empty")

    # Validate cta
    cta = structured_data.get("cta", {})
    if isinstance(cta, dict):
        if not cta.get("heading"):
            warnings.append("EMPTY_FIELD: cta.heading is empty")
        if not cta.get("button_label"):
            warnings.append("EMPTY_FIELD: cta.button_label is empty")
    elif cta:
        warnings.append("INVALID_COMPONENT: cta is not a dict")

    # Validate faq
    faq = structured_data.get("faq", [])
    if isinstance(faq, list):
        for i, item in enumerate(faq):
            if not isinstance(item, dict):
                warnings.append(f"INVALID_COMPONENT: faq[{i}] is not a dict")
                continue
            if not item.get("question"):
                warnings.append(f"EMPTY_FIELD: faq[{i}].question is empty")
            if not item.get("answer"):
                warnings.append(f"EMPTY_FIELD: faq[{i}].answer is empty")

    # Placeholder content detection
    _check_placeholders(structured_data, warnings)

    return warnings


def _check_placeholders(structured_data: dict, warnings: list[str]) -> None:
    """Check for placeholder/demo content in structured data."""
    # Check h1
    h1 = (structured_data.get("h1") or "").lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern in h1:
            warnings.append(f"PLACEHOLDER_CONTENT: h1 contains '{pattern}'")

    # Check quick_answer
    qa = (structured_data.get("quick_answer") or "").lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern in qa:
            warnings.append(f"PLACEHOLDER_CONTENT: quick_answer contains '{pattern}'")

    # Check capabilities for placeholder content
    for i, cap in enumerate(structured_data.get("capabilities", [])):
        if isinstance(cap, dict):
            title = (cap.get("title") or "").lower()
            desc = (cap.get("description") or "").lower()
            for pattern in _PLACEHOLDER_PATTERNS:
                if pattern in title or pattern in desc:
                    warnings.append(f"PLACEHOLDER_CONTENT: capabilities[{i}] contains '{pattern}'")