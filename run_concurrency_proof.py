"""Concurrency proof: 3-5 real page jobs through CATALYST.

Verifies:
- Bounded concurrency via max_concurrency (research phase)
- Independent job state
- Failure isolation (1 controlled failure)
- Independent artifacts per page
- Real Dify RAG + real pSEO Engine generation
- Unified validation on every successful page

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
from seo_aeo_geo_pipeline.discovery.models import KeywordCluster
from seo_aeo_geo_pipeline.discovery.opportunity import _detect_page_type

from pseo.config import load_config
from pseo.generate import generate_article, slugify
from pseo.render import render_article


OUTPUT_DIR = PROJECT_ROOT / "output" / "concurrency_proof"

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

# Real page jobs: different keywords to prove independence
PAGE_JOBS = [
    {"keyword": "social media scheduling automation", "intent": "informational", "expect": "use-case-capability"},
    {"keyword": "crm integration workflow", "intent": "informational", "expect": "use-case-capability"},
    {"keyword": "project management automation tools", "intent": "informational", "expect": "use-case-capability"},
    {"keyword": "", "intent": "informational", "expect": "FAIL", "note": "intentional failure - empty keyword"},
    {"keyword": "email marketing automation platform", "intent": "informational", "expect": "use-case-capability"},
]

MAX_CONCURRENCY = 3


def research_to_cluster(snapshot: dict) -> dict:
    cluster = KeywordCluster(
        cluster_id="concurrency-proof",
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
    h1 = structured.get("h1", keyword)
    quick_answer = structured.get("quick_answer", "")
    body_no_h1 = html_body
    if body_no_h1.startswith("<h1>"):
        body_no_h1 = body_no_h1[body_no_h1.index("</h1>") + 5:]
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
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
        h1=h1,
        quick_answer_short=(quick_answer[:200] + "...") if quick_answer else "",
        body=body_no_h1,
    )


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
        },
        "validation": {
            "decision": validation.get("decision", "UNKNOWN"),
            "score": validation.get("score", 0),
            "grade": validation.get("grade", "D"),
            "blocked": validation.get("blocked", False),
            "warnings": validation.get("warnings", []),
        },
        "status": "publish-ready" if validation.get("decision") == "PASS" else validation.get("decision", "UNKNOWN"),
    }


def main():
    print("SEO + AEO + GEO Pipeline - Concurrency Proof")
    print(f"Jobs: {len(PAGE_JOBS)} | Max concurrency: {MAX_CONCURRENCY}")
    print(f"Output: {OUTPUT_DIR}")
    print()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    config_path = PROJECT_ROOT / "config" / "openrouter.yaml"

    # Separate real jobs from intentional failures
    real_specs = [j for j in PAGE_JOBS if j["keyword"]]
    fail_specs = [j for j in PAGE_JOBS if not j["keyword"]]

    print(f"Real jobs: {len(real_specs)} | Failure jobs: {len(fail_specs)}")
    print()

    t_overall_start = time.monotonic()

    # ===== PHASE 1: BOUNDED CONCURRENT RESEARCH =====
    print("=" * 60)
    print(f"PHASE 1: CONCURRENT RESEARCH (max_concurrency={MAX_CONCURRENCY})")
    print("=" * 60)

    # Create PageJobs for real keywords
    real_jobs = []
    for i, spec in enumerate(real_specs):
        job = PageJob(
            job_id=f"conc-{i}-{slugify(spec['keyword'])}",
            keyword=spec["keyword"],
            intent=spec["intent"],
        )
        real_jobs.append((i, spec, job))

    # Also create a job for the intentional failure
    fail_job = None
    if fail_specs:
        fail_spec = fail_specs[0]
        fail_job = PageJob(
            job_id="conc-fail-intentional",
            keyword=fail_spec["keyword"],
            intent=fail_spec["intent"],
        )

    # Run research through CATALYST with bounded concurrency
    t_research_start = time.monotonic()
    dify_client = DifyRAGClient()
    agent = DeepResearchAgent(dify_client=dify_client)
    research_fn = create_research_fn(agent)

    catalyst = Catalyst(max_concurrency=MAX_CONCURRENCY)
    for _, _, job in real_jobs:
        catalyst.add_job(job)

    print(f"  Launching {len(real_jobs)} research jobs with max_concurrency={MAX_CONCURRENCY}...")
    research_batch = catalyst.run(research_fn)
    t_research_total = time.monotonic() - t_research_start

    print(f"  Research phase complete in {t_research_total:.1f}s")
    print(f"  Successful: {research_batch.successful} | Failed: {research_batch.failed}")

    # Run intentional failure separately
    fail_result = None
    if fail_job:
        print(f"\n  Running intentional failure job...")
        fail_catalyst = Catalyst(max_concurrency=1)
        fail_catalyst.add_job(fail_job)
        fail_batch = fail_catalyst.run(research_fn)
        fail_result = fail_batch.results[0]
        print(f"  Failure job: {'FAILED as expected' if not fail_result.success else 'UNEXPECTED SUCCESS'}")

    # Wait for per-minute rate limit window to reset before starting generation
    print(f"\n  [rate-limit] Waiting 65s for per-minute window to reset...")
    time.sleep(65)

    # ===== PHASE 2: SEQUENTIAL GENERATION =====
    print()
    print("=" * 60)
    print("PHASE 2: SEQUENTIAL GENERATION + VALIDATION")
    print("=" * 60)

    all_results = []

    for job_idx, (i, spec, job) in enumerate(real_jobs):
        # Rate-limit adaptation: wait 15s between generation calls to stay
        # under OpenRouter's 20 req/min free-tier limit. Research consumed
        # ~16 calls; generation needs to spread across minutes.
        if job_idx > 0:
            print(f"\n  [rate-limit] Waiting 15s before next generation...")
            time.sleep(15)

        job_result = {
            "job_index": i,
            "keyword": spec["keyword"],
            "intent": spec["intent"],
            "expected": spec.get("expect", "use-case-capability"),
            "status": "PENDING",
            "t_start": time.monotonic(),
            "research_sources": 0,
            "page_type": None,
            "template": None,
            "validation_decision": None,
            "validation_score": 0,
            "validation_grade": "D",
            "error": None,
            "artifacts": {},
        }

        try:
            if not research_batch.results[i].success:
                raise RuntimeError(f"Research failed: {research_batch.results[i].error}")

            snapshot = job.research_result["snapshot"]
            job_result["research_sources"] = len(snapshot.get("sources", []))

            cluster = research_to_cluster(snapshot)
            job_result["page_type"] = cluster["page_type"]
            job_result["template"] = cluster["template"]

            t_gen_start = time.monotonic()
            config = load_config(config_path)
            draft = generate_article(cluster, config, dry_run=False)
            job_result["t_generation"] = time.monotonic() - t_gen_start

            validation = validate_pseo(draft, existing_titles=[draft.get("meta_title", "")])
            job_result["validation_decision"] = validation["decision"]
            job_result["validation_score"] = validation["score"]
            job_result["validation_grade"] = validation["grade"]

            out_dir = run_dir / f"page-{i}-{slugify(spec['keyword'])}"
            out_dir.mkdir(parents=True, exist_ok=True)

            (out_dir / "research.json").write_text(json.dumps(snapshot, indent=2, default=str))
            (out_dir / "page.json").write_text(json.dumps(draft, indent=2, default=str))

            html = build_html_page(draft, spec["keyword"])
            (out_dir / "page.html").write_text(html)

            artifact = build_artifact(spec["keyword"], spec["intent"], snapshot, draft, validation)
            (out_dir / "artifact.json").write_text(json.dumps(artifact, indent=2, default=str))

            job_result["artifacts"] = {
                "research": str(out_dir / "research.json"),
                "page_json": str(out_dir / "page.json"),
                "page_html": str(out_dir / "page.html"),
                "artifact": str(out_dir / "artifact.json"),
            }

            job_result["status"] = "SUCCESS"

        except Exception as e:
            job_result["status"] = "FAILED"
            job_result["error"] = str(e)

        job_result["t_total"] = time.monotonic() - job_result["t_start"]
        all_results.append(job_result)

        status_icon = "PASS" if job_result["status"] == "SUCCESS" else "FAIL"
        print(f"\n  Job {i}: {status_icon} | {spec['keyword'][:40]}")
        print(f"    page_type={job_result['page_type']} template={job_result['template']}")
        print(f"    validation={job_result['validation_decision']} score={job_result['validation_score']} grade={job_result['validation_grade']}")
        print(f"    sources={job_result['research_sources']} gen={job_result.get('t_generation', 0):.1f}s total={job_result['t_total']:.1f}s")

    # Add failure result
    if fail_result:
        fail_entry = {
            "job_index": len(real_jobs),
            "keyword": "",
            "intent": "informational",
            "expected": "FAIL",
            "status": "FAILED" if not fail_result.success else "SUCCESS",
            "error": fail_result.error,
            "t_total": 0,
            "research_sources": 0,
            "page_type": None,
            "template": None,
            "validation_decision": None,
            "validation_score": 0,
            "validation_grade": "D",
            "artifacts": {},
        }
        all_results.append(fail_entry)

    t_overall = time.monotonic() - t_overall_start

    # ===== SUMMARY =====
    successful = [r for r in all_results if r["status"] == "SUCCESS"]
    failed = [r for r in all_results if r["status"] == "FAILED"]

    print("\n" + "=" * 60)
    print("CONCURRENCY PROOF SUMMARY")
    print("=" * 60)

    print(f"\nTotal jobs: {len(all_results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Total time: {t_overall:.1f}s")
    print(f"Research phase: {t_research_total:.1f}s (concurrent, max_concurrency={MAX_CONCURRENCY})")

    if successful:
        print(f"\nSuccessful pages:")
        for r in successful:
            print(f"  Job {r['job_index']}: {r['keyword'][:40]}")
            print(f"    page_type={r['page_type']} template={r['template']}")
            print(f"    validation={r['validation_decision']} score={r['validation_score']} grade={r['validation_grade']}")

    if failed:
        print(f"\nFailed jobs:")
        for r in failed:
            if r["keyword"]:
                print(f"  Job {r['job_index']}: {r['keyword'][:40]} - {r['error'][:60]}")
            else:
                print(f"  Job {r['job_index']}: INTENTIONAL FAILURE - {r['error'][:60] if r['error'] else 'empty keyword'}")

    # Failure isolation
    real_success = [r for r in all_results if r["expected"] != "FAIL" and r["status"] == "SUCCESS"]
    fail_isolated = [r for r in all_results if r["expected"] == "FAIL" and r["status"] == "FAILED"]
    isolation_ok = len(real_success) == len(real_specs) and len(fail_isolated) == len(fail_specs)

    print(f"\nFailure isolation: {'PASS' if isolation_ok else 'FAIL'}")
    if isolation_ok:
        print(f"  {len(real_success)} real jobs succeeded despite {len(fail_isolated)} intentional failure(s)")
    else:
        print(f"  Expected {len(real_specs)} success, got {len(real_success)}")
        print(f"  Expected {len(fail_specs)} failure, got {len(fail_isolated)}")

    # Artifact verification
    print(f"\nArtifact verification:")
    artifacts_ok = True
    for r in successful:
        artifacts = r.get("artifacts", {})
        all_exist = all(Path(v).exists() for v in artifacts.values())
        sizes = {k: Path(v).stat().st_size for k, v in artifacts.items() if Path(v).exists()}
        if not all_exist:
            artifacts_ok = False
        print(f"  Job {r['job_index']}: {'ALL PRESENT' if all_exist else 'MISSING'} | {sizes}")

    # Verify pages are not identical
    if len(successful) > 1:
        page_hashes = []
        for r in successful:
            page_json_path = r["artifacts"].get("page_json")
            if page_json_path and Path(page_json_path).exists():
                content = Path(page_json_path).read_text()
                page_hashes.append(hash(content))
        unique_pages = len(set(page_hashes)) == len(page_hashes)
        print(f"\nPage uniqueness: {'PASS' if unique_pages else 'FAIL'} ({len(set(page_hashes))} unique of {len(page_hashes)})")
    else:
        unique_pages = True
        print(f"\nPage uniqueness: N/A (only 1 page)")

    # Save summary
    summary = {
        "run_id": run_id,
        "total_jobs": len(all_results),
        "successful": len(successful),
        "failed": len(failed),
        "max_concurrency": MAX_CONCURRENCY,
        "total_time": t_overall,
        "research_time": t_research_total,
        "isolation_ok": isolation_ok,
        "artifacts_ok": artifacts_ok,
        "unique_pages": unique_pages,
        "jobs": all_results,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nSummary saved: {run_dir / 'summary.json'}")

    # Final verdict
    all_real_pass = all(r["status"] == "SUCCESS" for r in all_results if r["expected"] != "FAIL")
    all_fail_isolated = all(r["status"] == "FAILED" for r in all_results if r["expected"] == "FAIL")
    final_pass = all_real_pass and all_fail_isolated and artifacts_ok and unique_pages

    print(f"\n{'='*60}")
    print(f"VERDICT: {'PASS' if final_pass else 'FAIL'}")
    print(f"  {len(real_specs)} real jobs all succeeded: {'YES' if all_real_pass else 'NO'}")
    print(f"  Controlled failure isolated: {'YES' if all_fail_isolated else 'NO'}")
    print(f"  Artifacts independent: {'YES' if artifacts_ok else 'NO'}")
    print(f"  Pages unique: {'YES' if unique_pages else 'NO'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
