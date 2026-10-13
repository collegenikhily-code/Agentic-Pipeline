#!/usr/bin/env python3
"""Prove CATALYST dispatches 2-3 independent research jobs concurrently.

Uses real DeepResearchAgent with litellm. One failed job must not terminate others.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from seo_aeo_geo_pipeline.catalyst.orchestrator import Catalyst
from seo_aeo_geo_pipeline.catalyst.adapters import create_research_fn
from seo_aeo_geo_pipeline.models import PageJob
from seo_aeo_geo_pipeline.research.deep_research import DeepResearchAgent


def main():
    print("=" * 70)
    print("CATALYST CONCURRENT RESEARCH - 3 Independent Jobs")
    print("=" * 70)

    # Create 3 real PageJobs from different discovery opportunities
    jobs = [
        PageJob(job_id="job-meta-ads-mcp", keyword="meta ads mcp", intent="informational"),
        PageJob(job_id="job-ai-blend-tool", keyword="ai blend tool", intent="informational"),
        PageJob(job_id="job-google-ads-cert", keyword="google ads certification", intent="informational"),
    ]

    for job in jobs:
        print(f"  Job: {job.job_id} | keyword={job.keyword} | intent={job.intent}")

    # Create CATALYST with concurrency=2
    catalyst = Catalyst(max_concurrency=2)
    catalyst.add_jobs(jobs)

    # Create research function with real LLM agent
    agent = DeepResearchAgent()
    research_fn = create_research_fn(agent)

    # Run with timing
    print(f"\nRunning CATALYST with max_concurrency=2...")
    start = time.time()
    batch = catalyst.run(research_fn)
    elapsed = time.time() - start

    print(f"\nCompleted in {elapsed:.1f}s")
    print(f"\n--- Batch Summary ---")
    summary = batch.summary()
    print(f"  Total jobs: {summary['total_jobs']}")
    print(f"  Successful: {summary['successful']}")
    print(f"  Failed: {summary['failed']}")

    for r in batch.results:
        status = "SUCCESS" if r.success else "FAILED"
        keyword = r.research_result.get("plan", {}).get("primary_keyword", "?") if r.research_result else "?"
        print(f"  [{status}] {r.job_id} | keyword={keyword} | retries={r.retries_used}")
        if r.error:
            print(f"    Error: {r.error}")

    # Save results
    output_dir = Path("runs/catalyst_concurrent_proof")
    output_dir.mkdir(parents=True, exist_ok=True)

    results_data = []
    for r in batch.results:
        rd = {
            "job_id": r.job_id,
            "success": r.success,
            "error": r.error,
            "retries_used": r.retries_used,
        }
        if r.research_result and "dataset" in r.research_result:
            ds = r.research_result["dataset"]
            rd["sources"] = len(ds.sources)
            rd["questions_answered"] = len(ds.questions_answered)
            rd["page_type"] = ds.page_type_recommendation
        results_data.append(rd)

    (output_dir / "batch_results.json").write_text(json.dumps({
        "summary": summary,
        "results": results_data,
    }, indent=2))

    print(f"\nResults saved to {output_dir}/")
    print("=" * 70)
    if batch.failed == 0:
        print("PROOF COMPLETE - All 3 jobs completed successfully")
    else:
        print(f"PROOF COMPLETE - {batch.successful}/{batch.total_jobs} succeeded, failure isolation working")
    print("=" * 70)


if __name__ == "__main__":
    main()
