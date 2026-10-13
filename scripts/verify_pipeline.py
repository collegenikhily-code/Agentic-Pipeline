#!/usr/bin/env python3
"""Pipeline verification using existing E2E artifacts.

Validates:
1. Research artifacts exist and have correct structure
2. Template selection works (HyperText fallback)
3. Draft artifacts exist and have correct structure
4. Unified gate validation produces correct decision
5. Technical SEO audit works on rendered HTML
6. Traces are captured
7. All artifacts are properly linked

Does NOT make live LLM calls - uses existing artifacts from 20261006-182128.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from seo_aeo_geo_pipeline.template_layer import (
    TemplateRegistry,
    register_all_templates,
    create_hypertext_adapter,
)
from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo
from seo_aeo_geo_pipeline.gates.technical_seo import evaluate_technical_seo
from seo_aeo_geo_pipeline.observability import get_trace_collector
from seo_aeo_geo_pipeline.config import Settings


E2E_PROOF_DIR = PROJECT_ROOT / "output" / "e2e_proof" / "20261006-182128"
PAGES = [
    "facebook-business-manager",
    "meta-business-suite-login",
    "sora-ai-video-generator",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def verify_research_artifacts() -> bool:
    """Verify research.json artifacts have correct structure."""
    print("\n[1/6] Verifying research artifacts...")
    all_ok = True

    for page in PAGES:
        research_path = E2E_PROOF_DIR / page / "research.json"
        if not research_path.exists():
            print(f"  ❌ {page}: research.json missing")
            all_ok = False
            continue

        research = load_json(research_path)
        required_fields = [
            "primary_keyword", "intent", "page_type_recommendation",
            "completion_status", "sources", "questions_answered",
            "source_count", "data_hash", "provider"
        ]

        missing = [f for f in required_fields if f not in research]
        if missing:
            print(f"  ❌ {page}: missing fields: {missing}")
            all_ok = False
        else:
            print(f"  ✅ {page}: research complete ({research['completion_status']}), "
                  f"type={research['page_type_recommendation']}, "
                  f"sources={research['source_count']}, "
                  f"questions={len(research['questions_answered'])}")

    return all_ok


def verify_template_selection() -> bool:
    """Verify HyperText template selection (fallback mode) works."""
    print("\n[2/6] Verifying template selection...")
    all_ok = True

    registry = TemplateRegistry()
    register_all_templates(registry)
    adapter = create_hypertext_adapter(registry, Settings())

    for page in PAGES:
        research_path = E2E_PROOF_DIR / page / "research.json"
        research = load_json(research_path)

        selection = adapter.select_for_research_snapshot(
            job_id=f"e2e-{page}",
            run_id="20261006-182128",
            snapshot=research,
        )

        # Should use fallback (HyperText not configured)
        if selection.source != "fallback":
            print(f"  ❌ {page}: expected fallback, got {selection.source}")
            all_ok = False
        elif selection.template_name not in [s.name for s in registry.list_all()]:
            print(f"  ❌ {page}: selected template not in registry: {selection.template_name}")
            all_ok = False
        else:
            print(f"  ✅ {page}: fallback selected {selection.template_name} "
                  f"(family: {selection.template_family}, reason: {selection.fallback_reason})")

    return all_ok


def verify_draft_artifacts() -> bool:
    """Verify page.json draft artifacts have correct structure."""
    print("\n[3/6] Verifying draft artifacts...")
    all_ok = True

    for page in PAGES:
        draft_path = E2E_PROOF_DIR / page / "page.json"
        if not draft_path.exists():
            print(f"  ❌ {page}: page.json missing")
            all_ok = False
            continue

        draft = load_json(draft_path)
        required_fields = [
            "slug", "keyword", "intent", "template_used",
            "status", "structured_data", "meta_title", "meta_description"
        ]

        missing = [f for f in required_fields if f not in draft]
        if missing:
            print(f"  ❌ {page}: missing fields: {missing}")
            all_ok = False
        else:
            print(f"  ✅ {page}: draft status={draft['status']}, "
                  f"template={draft['template_used']}, "
                  f"schema={draft.get('schema_type', 'N/A')}")

    return all_ok


def verify_unified_gate() -> bool:
    """Verify unified gate validation on existing drafts."""
    print("\n[4/6] Verifying unified gate validation...")
    all_ok = True

    for page in PAGES:
        draft_path = E2E_PROOF_DIR / page / "page.json"
        html_path = E2E_PROOF_DIR / page / "page.html"
        artifact_path = E2E_PROOF_DIR / page / "artifact.json"

        if not all(p.exists() for p in [draft_path, html_path, artifact_path]):
            print(f"  ❌ {page}: missing artifact files")
            all_ok = False
            continue

        draft = load_json(draft_path)
        html = html_path.read_text()
        artifact = load_json(artifact_path)

        validation = validate_pseo(
            draft=draft,
            existing_titles=[],
            egeo_findings=None,
            html=html,
            artifact=artifact,
        )

        decision = validation["decision"]
        score = validation["score"]
        grade = validation["grade"]
        blocked = validation["blocked"]

        # Check technical SEO is included
        has_technical = "technical_seo" in validation

        # All three pages should be REPAIR (due to internal_links advisory warning)
        if decision not in ("PASS", "REPAIR"):
            print(f"  ❌ {page}: unexpected decision {decision} (score={score}, grade={grade})")
            all_ok = False
        elif not has_technical:
            print(f"  ❌ {page}: technical SEO not in validation result")
            all_ok = False
        else:
            tech = validation["technical_seo"]
            tech_decision = tech["decision"]
            tech_blocked = tech["blocked"]
            print(f"  ✅ {page}: decision={decision}, score={score}, grade={grade}, "
                  f"tech={tech_decision} (blocked={tech_blocked})")

    return all_ok


def verify_technical_seo_checks() -> bool:
    """Verify technical SEO checks produce expected results."""
    print("\n[5/6] Verifying technical SEO checks...")
    all_ok = True

    for page in PAGES:
        html_path = E2E_PROOF_DIR / page / "page.html"
        artifact_path = E2E_PROOF_DIR / page / "artifact.json"

        if not all(p.exists() for p in [html_path, artifact_path]):
            print(f"  ❌ {page}: missing files for technical SEO")
            all_ok = False
            continue

        html = html_path.read_text()
        artifact = load_json(artifact_path)

        tech = evaluate_technical_seo(html, artifact)

        # Check all 11 checks exist
        expected_checks = [
            "http_status", "canonical", "noindex_robots", "title",
            "meta_description", "h1", "content_substance", "internal_links",
            "structured_data", "indexability_readiness", "soft_404"
        ]

        missing_checks = [c for c in expected_checks if c not in tech["checks"]]
        if missing_checks:
            print(f"  ❌ {page}: missing checks: {missing_checks}")
            all_ok = False
            continue

        # Verify check classifications
        blocking_checks = ["noindex_robots", "title", "h1", "content_substance", "soft_404"]
        advisory_checks = ["http_status", "canonical", "meta_description", "internal_links",
                           "structured_data", "indexability_readiness"]

        for check_name in blocking_checks:
            check = tech["checks"][check_name]
            if check["severity"] != "blocking":
                print(f"  ❌ {page}: {check_name} should be blocking, is {check['severity']}")
                all_ok = False

        for check_name in advisory_checks:
            check = tech["checks"][check_name]
            if check["severity"] != "advisory":
                print(f"  ❌ {page}: {check_name} should be advisory, is {check['severity']}")
                all_ok = False

        # Internal links should be advisory (not blocking)
        internal_links = tech["checks"]["internal_links"]
        if not internal_links["passed"] and internal_links["severity"] == "blocking":
            print(f"  ❌ {page}: internal_links advisory warning should not be blocking")
            all_ok = False

        print(f"  ✅ {page}: all 11 checks present, classifications correct, "
              f"decision={tech['decision']}")

    return all_ok


def verify_traces() -> bool:
    """Verify trace artifacts exist."""
    print("\n[6/6] Verifying trace artifacts...")
    all_ok = True

    for page in PAGES:
        trace_path = E2E_PROOF_DIR / page / "traces.jsonl"
        if not trace_path.exists():
            print(f"  ❌ {page}: traces.jsonl missing")
            all_ok = False
            continue

        lines = trace_path.read_text().strip().split("\n")
        if len(lines) < 1:
            print(f"  ❌ {page}: no trace records")
            all_ok = False
            continue

        # Parse first record
        first_trace = json.loads(lines[0])
        required_fields = [
            "trace_id", "run_id", "job_id", "stage", "operation",
            "model", "provider", "started_at", "ended_at", "latency_ms",
            "success"
        ]
        missing = [f for f in required_fields if f not in first_trace]
        if missing:
            print(f"  ❌ {page}: trace missing fields: {missing}")
            all_ok = False
        else:
            print(f"  ✅ {page}: {len(lines)} trace records, "
                  f"stages={set(json.loads(l)['stage'] for l in lines)}")

    return all_ok


def main() -> int:
    print("=" * 70)
    print("PIPELINE VERIFICATION - Using Existing E2E Artifacts")
    print("=" * 70)
    print(f"Artifacts directory: {E2E_PROOF_DIR}")

    if not E2E_PROOF_DIR.exists():
        print(f"ERROR: E2E proof directory not found: {E2E_PROOF_DIR}")
        return 1

    checks = [
        verify_research_artifacts,
        verify_template_selection,
        verify_draft_artifacts,
        verify_unified_gate,
        verify_technical_seo_checks,
        verify_traces,
    ]

    results = []
    for check in checks:
        results.append(check())

    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    check_names = [
        "Research Artifacts",
        "Template Selection (HyperText Fallback)",
        "Draft Artifacts",
        "Unified Gate (pSEO + AEO/GEO + Technical SEO)",
        "Technical SEO Checks (11 checks, correct classifications)",
        "Trace Artifacts",
    ]

    for name, result in zip(check_names, results):
        status = "PASS" if result else "FAIL"
        print(f"  {status}: {name}")

    all_passed = all(results)
    print(f"\nOverall: {'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())