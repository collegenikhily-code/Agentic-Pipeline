#!/usr/bin/env python3
"""Complete pipeline integration: Discovery → Intelligence → Dify → Deep Research → CATALYST → HyperText → pSEO Engine → Unified Gates → Technical SEO → HTML → LetterTrace.

Usage:
    python scripts/run_full_pipeline.py --keyword "best CRM for textile manufacturers" --intent commercial

Environment:
    HYPERTEXT_API_KEY - optional, for HyperText template selection
    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY - optional, for Langfuse tracing
    LETTERTRACE_API_KEY - optional, for LetterTrace monitoring
    DIFY_API_KEY, DIFY_DATASET_ID - optional, for Dify knowledge retrieval
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add project root and pSEO engine to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT.parent / "pseo-engine-oss" / "pipeline"))

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Core pipeline imports
from seo_aeo_geo_pipeline.models import PageJob
from seo_aeo_geo_pipeline.catalyst import Catalyst, create_research_fn
from seo_aeo_geo_pipeline.research.deep_research import DeepResearchAgent
from seo_aeo_geo_pipeline.research.dify_rag import DifyRAGClient
from seo_aeo_geo_pipeline.template_layer import (
    TemplateRegistry,
    register_all_templates,
    create_hypertext_adapter,
)
from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo
from seo_aeo_geo_pipeline.gates.technical_seo import evaluate_technical_seo
from seo_aeo_geo_pipeline.observability import (
    set_trace_context,
    register_langfuse_sink,
    register_lettertrace_sink,
    get_trace_collector,
    trace_context,
)
from seo_aeo_geo_pipeline.config import Settings

# pSEO Engine imports
from pseo.config import load_config
from pseo.generate import generate_article
from pseo.render import render_article


def research_snapshot_to_cluster(snapshot: dict) -> dict:
    """Convert research snapshot to pSEO Engine cluster format."""
    return {
        "primary_keyword": snapshot["primary_keyword"],
        "keyword": snapshot["primary_keyword"],
        "intent": snapshot["intent"],
        "template": snapshot.get("page_type_recommendation", "comparison-guide"),
    }


def build_research_fn(
    dify_client: DifyRAGClient | None = None,
    competitor_intel: object | None = None,
) -> callable:
    """Build a research function that uses DeepResearchAgent with optional Dify and competitor intel."""
    from seo_aeo_geo_pipeline.catalyst.adapters import create_research_fn
    agent = DeepResearchAgent(
        dify_client=dify_client,
        competitor_intel=competitor_intel,
    )
    return create_research_fn(agent)


def run_full_pipeline(
    keyword: str,
    intent: str,
    config_path: str,
    output_dir: str,
    run_id: str | None = None,
    enable_langfuse: bool = False,
    enable_lettertrace: bool = False,
) -> dict:
    """Execute the complete pipeline with all stages."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    run_id = run_id or f"run-{int(time.time())}"
    job_id = f"job-{int(time.time() * 1000) % 100000}"

    # Initialize tracing
    set_trace_context(run_id=run_id, job_id=job_id, stage="pipeline")
    if enable_langfuse:
        register_langfuse_sink()
    if enable_lettertrace:
        register_lettertrace_sink()

    print("=" * 70)
    print(f"FULL PIPELINE RUN: {run_id}")
    print(f"Keyword: {keyword} | Intent: {intent}")
    print("=" * 70)

    t_start = time.monotonic()

    # ── Step 1: Initialize components ────────────────────────────────────────
    print("\n[1/8] Initializing components...")

    # Dify client (graceful fallback if not configured)
    dify_client = DifyRAGClient()
    if dify_client.is_configured:
        print(f"  Dify: configured (dataset={dify_client.dataset_id})")
    else:
        print("  Dify: not configured (graceful fallback)")

    # Template registry
    registry = TemplateRegistry()
    register_all_templates(registry)
    print(f"  Templates registered: {len(registry.list_all())} across {len(registry.families())} families")

    # HyperText adapter
    hypertext_adapter = create_hypertext_adapter(registry, Settings())
    print(f"  HyperText: {'configured' if hypertext_adapter.hypertext_configured else 'fallback mode'}")

    # Langfuse
    if enable_langfuse:
        print("  Langfuse: sink registered")
    else:
        print("  Langfuse: disabled (set LANGFUSE_PUBLIC_KEY/SECRET_KEY to enable)")

    # LetterTrace
    if enable_lettertrace:
        print("  LetterTrace: sink registered")
    else:
        print("  LetterTrace: disabled (set LETTERTRACE_API_KEY to enable)")

    # ── Step 2: Research via CATALYST ────────────────────────────────────────
    print(f"\n[2/8] Researching: {keyword}")
    with trace_context(run_id=run_id, job_id=job_id, stage="research"):
        research_fn = build_research_fn(dify_client=dify_client)
        job = PageJob(job_id=job_id, keyword=keyword, intent=intent)
        catalyst = Catalyst(max_concurrency=1)
        catalyst.add_job(job)
        batch = catalyst.run(research_fn)

    if not batch.results[0].success:
        raise RuntimeError(f"Research failed: {batch.results[0].error}")

    snapshot = job.research_result["snapshot"]
    print(f"  Research complete ({snapshot['completion_status']}), page_type={snapshot['page_type_recommendation']}")
    print(f"  Sources: {snapshot['source_count']}, Questions answered: {len(snapshot.get('questions_answered', []))}")

    # Save research artifact
    (output / "research.json").write_text(json.dumps(snapshot, indent=2))

    # ── Step 3: HyperText Template Selection ─────────────────────────────────
    print("\n[3/8] HyperText template selection...")
    with trace_context(run_id=run_id, job_id=job_id, stage="template_selection"):
        selection_result = hypertext_adapter.select_for_research_snapshot(job_id, run_id, snapshot)

    print(f"  Selected: {selection_result.template_name} (family: {selection_result.template_family})")
    print(f"  Source: {selection_result.source}")
    if selection_result.source == "fallback":
        print(f"  Fallback reason: {selection_result.fallback_reason}")

    # Validate template exists in registry
    template_spec = registry.get(selection_result.template_name)
    if not template_spec:
        raise RuntimeError(f"Selected template '{selection_result.template_name}' not found in registry")

    # Save selection artifact
    (output / "template_selection.json").write_text(json.dumps({
        "template_name": selection_result.template_name,
        "template_family": selection_result.template_family,
        "confidence": selection_result.confidence,
        "source": selection_result.source,
        "fallback_reason": selection_result.fallback_reason,
        "hypertext_request_id": selection_result.hypertext_request_id,
        "hypertext_latency_ms": selection_result.hypertext_latency_ms,
    }, indent=2))

    # ── Step 4: Convert to pSEO Engine cluster ───────────────────────────────
    print("\n[4/8] Converting to pSEO Engine cluster...")
    cluster = research_snapshot_to_cluster(snapshot)
    cluster["template"] = selection_result.template_name
    print(f"  Cluster: {json.dumps(cluster, indent=2)}")

    # ── Step 5: Load pSEO Engine config ──────────────────────────────────────
    print(f"\n[5/8] Loading pSEO Engine config: {config_path}")
    pseo_config = load_config(config_path)
    print(f"  Model: {pseo_config.generation.model}")

    # ── Step 6: Generate article via pSEO Engine ─────────────────────────────
    print("\n[6/8] Generating article via pSEO Engine...")
    with trace_context(run_id=run_id, job_id=job_id, stage="generation"):
        last_err = None
        for attempt in range(5):
            try:
                draft = generate_article(cluster, pseo_config, dry_run=False)
                break
            except Exception as e:
                last_err = e
                wait = 10 * (attempt + 1)
                print(f"  Attempt {attempt+1}/5 failed: {type(e).__name__}")
                if attempt < 4:
                    print(f"  Retrying in {wait}s...")
                    time.sleep(wait)
        else:
            raise last_err

    print(f"  Generation complete ({draft['status']})")

    # Save draft artifact
    (output / "page.json").write_text(json.dumps(draft, indent=2, default=str))

    # ── Step 7: Unified Gates (pSEO + AEO/GEO + Technical SEO) ───────────────
    print("\n[7/8] Running unified validation gates...")
    with trace_context(run_id=run_id, job_id=job_id, stage="validation"):
        # Render HTML first for technical SEO
        structured = draft.get("structured_data", {})
        html_body = render_article(selection_result.template_name, structured)
        html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{draft.get('meta_title', keyword)}</title>
<meta name="description" content="{draft.get('meta_description', '')}">
</head>
<body>
{html_body}
</body></html>"""

        (output / "page.html").write_text(html_page)

        # Create artifact dict for technical SEO
        artifact = {
            "slug": draft.get("slug"),
            "keyword": keyword,
            "intent": intent,
            "template": selection_result.template_name,
            "status": draft.get("status"),
            "schema_type": draft.get("schema_type"),
            "meta_title": draft.get("meta_title"),
            "meta_description": draft.get("meta_description"),
        }

        # Run unified gate (includes technical SEO)
        validation = validate_pseo(
            draft=draft,
            existing_titles=[],  # No existing titles in M1
            egeo_findings=None,
            html=html_page,
            artifact=artifact,
            research_snapshot=snapshot,
        )

    decision = validation["decision"]
    score = validation["score"]
    grade = validation["grade"]
    blocked = validation["blocked"]
    warnings = validation["warnings"]

    print(f"  Decision: {decision} (score={score}, grade={grade}, blocked={blocked})")
    if warnings:
        print(f"  Warnings: {len(warnings)}")
        for w in warnings[:5]:
            print(f"    - {w}")

    # Save validation artifact
    (output / "validation.json").write_text(json.dumps(validation, indent=2, default=str))

    # ── Step 8: Save final artifacts and trace export ────────────────────────
    print("\n[8/8] Saving artifacts...")

    # Export traces
    collector = get_trace_collector()
    traces = collector.get_records(run_id=run_id)
    if traces:
        trace_file = output / "traces.jsonl"
        with open(trace_file, "w") as f:
            for t in traces:
                f.write(json.dumps(t, default=str) + "\n")
        print(f"  Traces exported: {len(traces)} records → {trace_file}")

    # Final summary artifact
    summary = {
        "run_id": run_id,
        "job_id": job_id,
        "keyword": keyword,
        "intent": intent,
        "template": selection_result.template_name,
        "template_source": selection_result.source,
        "validation_decision": decision,
        "validation_score": score,
        "validation_grade": grade,
        "validation_blocked": blocked,
        "validation_warnings": warnings,
        "artifacts": {
            "research": str(output / "research.json"),
            "template_selection": str(output / "template_selection.json"),
            "draft": str(output / "page.json"),
            "html": str(output / "page.html"),
            "validation": str(output / "validation.json"),
            "traces": str(output / "traces.jsonl") if traces else None,
        },
        "timing": {
            "total_seconds": round(time.monotonic() - t_start, 2),
        },
        "environment": {
            "hypertext_configured": hypertext_adapter.hypertext_configured,
            "langfuse_enabled": enable_langfuse,
            "lettertrace_enabled": enable_lettertrace,
            "dify_configured": dify_client.is_configured,
        },
    }

    (output / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n{'='*70}")
    print("PIPELINE COMPLETE")
    print(f"{'='*70}")
    print(f"Run ID: {run_id}")
    print(f"Decision: {decision}")
    print(f"Score: {score} (Grade {grade})")
    print(f"Artifacts: {output}")
    print(f"Total time: {summary['timing']['total_seconds']:.1f}s")

    return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run full SEO pipeline")
    parser.add_argument("--keyword", required=True, help="Target keyword")
    parser.add_argument("--intent", default="informational", choices=["informational", "commercial", "transactional"])
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "openrouter.yaml"))
    parser.add_argument("--output", default=str(PROJECT_ROOT / "output" / "pipeline_run"))
    parser.add_argument("--run-id", help="Custom run ID")
    parser.add_argument("--langfuse", action="store_true", help="Enable Langfuse tracing")
    parser.add_argument("--lettertrace", action="store_true", help="Enable LetterTrace monitoring")
    args = parser.parse_args()

    try:
        summary = run_full_pipeline(
            keyword=args.keyword,
            intent=args.intent,
            config_path=args.config,
            output_dir=args.output,
            run_id=args.run_id,
            enable_langfuse=args.langfuse,
            enable_lettertrace=args.lettertrace,
        )
        sys.exit(0 if summary["validation_decision"] != "REJECT" else 1)
    except Exception as e:
        print(f"\nPIPELINE FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()