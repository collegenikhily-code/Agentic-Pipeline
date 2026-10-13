"""End-to-end proof: SEO + AEO + GEO content pipeline.

TARGET FLOW:
  SE Ranking discovery -> PageOpportunity -> CATALYST -> Deep Research
  -> PageSpec -> template selection -> pSEO Engine generation
  -> HTML/page artifact -> unified validation -> publish-ready artifact

Uses real: OpenRouter, Dify RAG, pSEO Engine. No mocks.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PSEO_ENGINE_ROOT = Path("/Users/nikhil/Documents/New OpenCode Project/pseo-engine-oss/pipeline")
if str(PSEO_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PSEO_ENGINE_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from seo_aeo_geo_pipeline.models import PageJob
from seo_aeo_geo_pipeline.catalyst import Catalyst, create_research_fn
from seo_aeo_geo_pipeline.research.deep_research import DeepResearchAgent
from seo_aeo_geo_pipeline.research.dify_rag import DifyRAGClient
from seo_aeo_geo_pipeline.gates.unified_gate import validate_pseo
from seo_aeo_geo_pipeline.discovery.models import KeywordCluster, PageOpportunity
from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type
from seo_aeo_geo_pipeline.observability.llm_trace import (
    get_trace_collector,
    set_trace_context,
    clear_trace_context,
)

from pseo.config import load_config
from pseo.generate import generate_article, slugify
from pseo.render import render_article


OUTPUT_DIR = PROJECT_ROOT / "output" / "e2e_proof"


# Template mapping: pipeline page_type -> pSEO Engine template name
TEMPLATE_MAP = {
    "comparison-guide": "comparison-guide",
    "product-how-to": "product-how-to",
    "role-guide": "reference-entry",
    "reference-entry": "reference-entry",
    "reference-page": "reference-entry",
    "problem-solution": "product-how-to",
    "best-listicle": "comparison-guide",
    "alternatives": "comparison-guide",
    "alternatives-page": "comparison-guide",
    "programmatic-entity": "reference-entry",
    "use-case-capability": "use-case-capability",
    "product-page": "comparison-guide",
    "guide": "reference-entry",
}


def load_opportunities_from_discovery(discovery_path: Path) -> list[dict]:
    """Load PageOpportunity objects from a discovery run's page_opportunities.json."""
    if not discovery_path.exists():
        raise FileNotFoundError(
            f"Discovery output not found: {discovery_path}\n"
            "Run discovery first: python scripts/discover_opportunities.py --competitor <domain>"
        )
    raw = json.loads(discovery_path.read_text())
    if not raw:
        raise ValueError(f"Discovery output is empty: {discovery_path}")
    return raw


def find_latest_discovery_run() -> Path | None:
    """Find the most recent discovery run with page_opportunities.json."""
    runs_dir = PROJECT_ROOT / "runs"
    if not runs_dir.exists():
        return None
    run_dirs = sorted(runs_dir.iterdir(), reverse=True)
    for run_dir in run_dirs:
        opp_file = run_dir / "discovery" / "raw" / "page_opportunities.json"
        if opp_file.exists():
            return opp_file
    return None


def research_to_cluster(snapshot: dict) -> dict:
    # Re-classify using the opportunity classifier (source of truth)
    # instead of the research agent's stale page_type_recommendation
    cluster = KeywordCluster(
        cluster_id="e2e",
        primary_keyword=snapshot["primary_keyword"],
        keywords=[snapshot["primary_keyword"]],
        dominant_intent=snapshot.get("intent", "informational"),
    )
    page_type = _detect_page_type(cluster, [])
    template = TEMPLATE_MAP.get(page_type, "comparison-guide")
    return {
        "primary_keyword": snapshot["primary_keyword"],
        "keyword": snapshot["primary_keyword"],
        "intent": snapshot["intent"],
        "page_type": page_type,
        "template": template,
    }


def build_html_page(draft: dict, keyword: str) -> str:
    structured = draft.get("structured_data", {})
    template_name = draft.get("template_used", "comparison-guide")
    html_body = render_article(template_name, structured)
    meta_title = draft.get("meta_title", keyword)
    meta_desc = draft.get("meta_description", "")
    slug = draft.get("slug", slugify(keyword))
    h1 = structured.get("h1", keyword)
    quick_answer = structured.get("quick_answer", "")
    schema_type = draft.get("schema_type", "")

    # Build JSON-LD from structured data for the dominant schema type
    json_ld = _build_json_ld(structured, schema_type, meta_title, meta_desc)

    # Remove duplicate H1 from rendered body (hero already has it)
    body_no_h1 = html_body
    if body_no_h1.startswith(f"<h1>"):
        body_no_h1 = body_no_h1[body_no_h1.index("</h1>") + 5:]
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://example.com/{slug}">
{json_ld}
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a2e; background: #fafafa; line-height: 1.7; }}
.hero {{ background: linear-gradient(135deg, #0f0f23 0%, #16213e 100%); color: #fff; padding: 4rem 2rem 3rem; margin: 0 0 2rem; border-radius: 0 0 20px 20px; }}
.hero h1 {{ font-size: 2.8rem; font-weight: 700; margin-bottom: 1rem; line-height: 1.2; }}
.hero p {{ color: rgba(255,255,255,0.85); font-size: 1.1rem; max-width: 640px; line-height: 1.6; }}
.container {{ max-width: 800px; margin: 0 auto; padding: 0 1.5rem 3rem; }}
h2 {{ font-size: 1.5rem; font-weight: 600; color: #16213e; margin: 2.5rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid #e8e8e8; }}
h3 {{ font-size: 1.15rem; font-weight: 600; color: #1a1a2e; margin: 1.5rem 0 0.5rem; }}
p {{ margin-bottom: 1rem; color: #333; }}
ul, ol {{ margin: 0.5rem 0 1rem 1.5rem; }}
li {{ margin-bottom: 0.4rem; color: #444; }}
strong {{ color: #1a1a2e; }}
section {{ background: #fff; border-radius: 12px; padding: 2rem; margin: 1.5rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.faq-item {{ background: #f8f9fa; border-radius: 8px; padding: 1.25rem; margin-bottom: 0.75rem; }}
.faq-item h3 {{ margin: 0 0 0.5rem; color: #16213e; }}
.faq-item p {{ margin: 0; }}
.key-signals li {{ background: #f0f4ff; padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 0.5rem; border-left: 3px solid #4361ee; }}
</style>
</head>
<body>
<div class="hero">
<div class="container">
<h1>{h1}</h1>
<p>{quick_answer_short}</p>
</div>
</div>
<div class="container">
{body}
</div>
</body>
</html>""".format(
        title=meta_title,
        desc=meta_desc,
        slug=slug,
        json_ld=json_ld,
        h1=h1,
        quick_answer_short=(quick_answer[:200] + "...") if quick_answer else "",
        body=body_no_h1,
    )


def _build_json_ld(structured: dict, schema_type: str, meta_title: str, meta_desc: str) -> str:
    """Build a JSON-LD script tag from structured data."""
    import json as _json

    faq = structured.get("faq", [])
    quick_answer = structured.get("quick_answer", "")
    h1 = structured.get("h1", meta_title)

    # Prefer FAQPage when FAQ items exist
    if faq and isinstance(faq, list):
        qa_items = []
        for item in faq:
            if isinstance(item, dict) and item.get("question") and item.get("answer"):
                qa_items.append({
                    "@type": "Question",
                    "name": item["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": item["answer"],
                    },
                })
        if qa_items:
            block = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": qa_items,
            }
            return f'<script type="application/ld+json">{_json.dumps(block)}</script>'

    # Fallback: Article / WebPage
    block = {
        "@context": "https://schema.org",
        "@type": "WebPage" if not schema_type or "Article" not in schema_type else "Article",
        "name": meta_title,
        "description": meta_desc,
        "headline": h1,
        "url": f"https://example.com/{slugify(h1)}",
    }
    if quick_answer:
        block["abstract"] = quick_answer
    return f'<script type="application/ld+json">{_json.dumps(block)}</script>'


def build_artifact(keyword, intent, snapshot, draft, validation):
    template_name = draft.get("template_used", "comparison-guide")
    slug = draft.get("slug", slugify(keyword))
    now = datetime.now(timezone.utc).isoformat()
    return {
        "artifact_version": "1.0",
        "generated_at": now,
        "keyword": keyword,
        "intent": intent,
        "slug": slug,
        "template": template_name,
        "seo": {
            "meta_title": draft.get("meta_title", ""),
            "meta_description": draft.get("meta_description", ""),
            "slug": slug,
            "schema_type": draft.get("schema_type", ""),
        },
        "research": {
            "primary_keyword": snapshot.get("primary_keyword", keyword),
            "page_type": snapshot.get("page_type_recommendation", ""),
            "sources_count": len(snapshot.get("sources", [])),
            "questions_answered": snapshot.get("questions_answered", []),
            "differentiation": snapshot.get("differentiation_strategy", ""),
            "audience": snapshot.get("audience_profile", ""),
            "completion_status": snapshot.get("completion_status", ""),
        },
        "validation": {
            "decision": validation.get("decision", "UNKNOWN"),
            "score": validation.get("score", 0),
            "grade": validation.get("grade", "D"),
            "blocked": validation.get("blocked", False),
            "warnings": validation.get("warnings", []),
        },
        "gate3_pseo": {
            "blocked": validation.get("gate3", {}).get("blocked", False),
            "guardrail_checks": len(validation.get("gate3", {}).get("guardrail_results", [])),
            "citability_score": validation.get("gate3", {}).get("citability_score", 0),
        },
        "gate4_aeo_geo": validation.get("gate4", {}),
        "technical_seo": validation.get("technical_seo", {}),
        "status": "publish-ready" if validation.get("decision") == "PASS" else validation.get("decision", "UNKNOWN"),
    }


def run_single_page(keyword, intent, config_path, output_dir, job_index=0):
    print(f"\n{'='*60}")
    print(f"[PAGE {job_index+1}] keyword={keyword!r} intent={intent}")
    print(f"{'='*60}")

    t_start = time.monotonic()

    # Trace context for this page
    run_id = time.strftime("%Y%m%d-%H%M%S")
    job_id = f"e2e-{job_index:03d}"
    set_trace_context(run_id=run_id, job_id=job_id, stage="research")

    # Step 1: Research via CATALYST + DeepResearchAgent
    print(f"\n[1/6] Researching: {keyword}")
    t0 = time.monotonic()

    dify_client = DifyRAGClient()
    agent = DeepResearchAgent(dify_client=dify_client)
    research_fn = create_research_fn(agent)
    job = PageJob(job_id=job_id, keyword=keyword, intent=intent)
    catalyst = Catalyst(max_concurrency=1)
    catalyst.add_job(job)
    batch = catalyst.run(research_fn)
    t_research = time.monotonic() - t0

    if not batch.results[0].success:
        print(f"  -> Research FAILED: {batch.results[0].error}")
        return None

    snapshot = job.research_result["snapshot"]
    print(f"  -> Research complete ({t_research:.1f}s)")
    print(f"     page_type={snapshot.get('page_type_recommendation', 'N/A')}")
    print(f"     sources={len(snapshot.get('sources', []))}")
    print(f"     completion_status={snapshot.get('completion_status', 'N/A')}")

    out_dir = output_dir / slugify(keyword)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "research.json").write_text(json.dumps(snapshot, indent=2, default=str))

    # Step 2: Convert to cluster
    print("\n[2/6] Building cluster from research")
    cluster = research_to_cluster(snapshot)
    print(f"  -> template={cluster['template']}")

    # Step 3: Load pSEO Engine config
    print("\n[3/6] Loading pSEO Engine config")
    config = load_config(config_path)
    print(f"  -> model={config.generation.model}")

    # Step 4: Generate article via pSEO Engine (REAL LLM call)
    print("\n[4/6] Generating article via pSEO Engine (real LLM)...")
    set_trace_context(stage="generation")
    t1 = time.monotonic()
    last_err = None
    for attempt in range(5):
        try:
            draft = generate_article(cluster, config, dry_run=False)
            break
        except Exception as e:
            last_err = e
            wait = 10 * (attempt + 1)
            print(f"  Attempt {attempt+1}/5 failed: {type(e).__name__}: {str(e)[:100]}")
            if attempt < 4:
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
    else:
        print(f"  -> Generation FAILED: {last_err}")
        return None
    t_generate = time.monotonic() - t1
    print(f"  -> Generation complete ({t_generate:.1f}s), status={draft.get('status')}")

    (out_dir / "page.json").write_text(json.dumps(draft, indent=2, default=str))

    # Step 5: Render HTML (before validation so technical SEO gate can run)
    print("\n[5/6] Rendering HTML for technical SEO gate...")
    html = build_html_page(draft, keyword)
    (out_dir / "page.html").write_text(html)
    print(f"  -> Saved: {out_dir / 'page.html'}")

    # Build artifact for technical SEO gate
    artifact = build_artifact(keyword, intent, snapshot, draft, {"decision": "PENDING"})

    # Step 6: Unified validation (includes technical SEO gate on rendered HTML)
    print("\n[6/6] Running unified validation (GATE 3 + GATE 4 + Technical SEO)...")
    existing_titles = [draft.get("meta_title", "")]
    validation = validate_pseo(draft, existing_titles=existing_titles, html=html, artifact=artifact)
    decision = validation["decision"]
    print(f"  -> Decision: {decision}")
    print(f"  -> Score: {validation['score']} (grade: {validation['grade']})")
    if "technical_seo" in validation:
        tech = validation["technical_seo"]
        print(f"  -> Technical SEO: {tech['decision']} (blocked={tech['blocked']})")
        for check_name, check_result in tech.get("checks", {}).items():
            status = "PASS" if check_result.get("passed") else "FAIL"
            sev = check_result.get("severity", "?")
            print(f"     [{status}/{sev}] {check_name}: {check_result.get('message', '')[:80]}")

    # Rebuild final artifact with actual validation result
    artifact = build_artifact(keyword, intent, snapshot, draft, validation)
    (out_dir / "artifact.json").write_text(json.dumps(artifact, indent=2, default=str))

    # Save LLM traces for this run
    print("\n[+] Saving LLM traces...")
    collector = get_trace_collector()
    traces = collector.get_records(run_id=run_id)
    if traces:
        trace_path = out_dir / "traces.jsonl"
        with open(trace_path, "w") as f:
            for tr in traces:
                f.write(json.dumps(tr, default=str) + "\n")
        print(f"  -> Saved {len(traces)} trace records to {trace_path}")

    clear_trace_context()

    t_total = time.monotonic() - t_start
    print(f"\n  DONE in {t_total:.1f}s | Decision: {decision} | Score: {validation['score']} | Grade: {validation['grade']}")
    print(f"  Artifacts: {out_dir}")

    return {
        "keyword": keyword,
        "intent": intent,
        "template": cluster["template"],
        "decision": decision,
        "score": validation["score"],
        "grade": validation["grade"],
        "t_research": t_research,
        "t_generate": t_generate,
        "t_total": t_total,
        "html_path": str(out_dir / "page.html"),
        "artifact_path": str(out_dir / "artifact.json"),
        "trace_path": str(out_dir / "traces.jsonl") if traces else None,
    }


def load_pages_from_opportunities(
    opportunities: list[dict],
    max_pages: int = 3,
) -> list[dict]:
    """Convert PageOpportunity dicts to page inputs for the pipeline."""
    pages = []
    for opp in opportunities[:max_pages]:
        keyword = opp.get("primary_keyword", "")
        intent = opp.get("intent", "informational")
        if not keyword:
            continue
        pages.append({
            "keyword": keyword,
            "intent": intent,
            "opportunity_id": opp.get("opportunity_id", ""),
            "search_volume": opp.get("search_volume", 0),
            "difficulty": opp.get("difficulty", 0),
            "recommended_page_type": opp.get("recommended_page_type", ""),
        })
    return pages


def main():
    import argparse

    parser = argparse.ArgumentParser(description="SEO + AEO + GEO Pipeline - E2E Proof")
    parser.add_argument(
        "--discovery",
        type=str,
        default=None,
        help="Path to page_opportunities.json from discovery run",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Maximum number of pages to generate",
    )
    parser.add_argument(
        "--keyword",
        type=str,
        default=None,
        help="Override: generate a single page for this keyword (bypasses discovery)",
    )
    parser.add_argument(
        "--intent",
        type=str,
        default="informational",
        help="Intent for --keyword override",
    )
    args = parser.parse_args()

    config_path = str(PROJECT_ROOT / "config" / "openrouter.yaml")
    output_dir = OUTPUT_DIR

    print("SEO + AEO + GEO Pipeline - E2E Proof")
    print(f"Config: {config_path}")

    # Load pages from discovery or keyword override
    if args.keyword:
        pages = [{"keyword": args.keyword, "intent": args.intent}]
    elif args.discovery:
        discovery_path = Path(args.discovery)
        opportunities = load_opportunities_from_discovery(discovery_path)
        pages = load_pages_from_opportunities(opportunities, max_pages=args.max_pages)
    else:
        # Auto-discover latest discovery run
        latest = find_latest_discovery_run()
        if latest is None:
            print("ERROR: No discovery data found.")
            print("Run discovery first:")
            print("  python scripts/discover_opportunities.py --competitor <domain>")
            print("Or provide --discovery <path> or --keyword <keyword>")
            sys.exit(1)
        print(f"Using discovery: {latest}")
        opportunities = load_opportunities_from_discovery(latest)
        pages = load_pages_from_opportunities(opportunities, max_pages=args.max_pages)

    if not pages:
        print("ERROR: No pages to generate.")
        sys.exit(1)

    # Use run-specific output directory
    run_id = time.strftime("%Y%m%d-%H%M%S")
    output_dir = OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output: {output_dir}")
    print(f"Pages: {len(pages)}")
    for p in pages:
        vol = p.get("search_volume", "?")
        diff = p.get("difficulty", "?")
        print(f"  - {p['keyword']!r} (intent={p['intent']}, vol={vol}, diff={diff})")

    results = []
    for i, page in enumerate(pages):
        result = run_single_page(
            keyword=page["keyword"],
            intent=page["intent"],
            config_path=config_path,
            output_dir=output_dir,
            job_index=i,
        )
        results.append(result)

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for r in results if r and r["decision"] == "PASS")
    repaired = sum(1 for r in results if r and r["decision"] == "REPAIR")
    rejected = sum(1 for r in results if r and r["decision"] == "REJECT")
    failed = sum(1 for r in results if r is None)

    print(f"Total: {len(pages)} | Pass: {passed} | Repair: {repaired} | Reject: {rejected} | Failed: {failed}")

    for r in results:
        if r:
            print(f"  {r['keyword']!r} -> {r['decision']} (score={r['score']}, grade={r['grade']}, template={r['template']})")
        else:
            print(f"  FAILED")

    return results


if __name__ == "__main__":
    main()
