"""Full vertical slice: Research → PageSpec → Template → pSEO Engine → HTML.

Uses OpenRouter (free model) through LiteLLM. No direct provider API calls.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure pSEO Engine is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pseo-engine-oss" / "pipeline"))

from seo_aeo_geo_pipeline.models import PageJob
from seo_aeo_geo_pipeline.catalyst import Catalyst, create_research_fn
from seo_aeo_geo_pipeline.research.agents import ResearchAgent

from pseo.config import load_config
from pseo.generate import generate_article
from pseo.render import render_article


def research_to_cluster(snapshot: dict) -> dict:
    """Convert a research snapshot to the cluster dict format expected by generate_article()."""
    return {
        "primary_keyword": snapshot["primary_keyword"],
        "keyword": snapshot["primary_keyword"],
        "intent": snapshot["intent"],
        "template": snapshot.get("page_type_recommendation", "comparison-guide"),
    }


def run_pipeline(keyword: str, intent: str, config_path: str, output_dir: str) -> dict:
    """Execute the full pipeline and save artifacts."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # Step 1: Research
    print(f"[1/5] Researching: {keyword}")
    t0 = time.monotonic()
    agent = ResearchAgent()
    research_fn = create_research_fn(agent)

    job = PageJob(job_id="slice-001", keyword=keyword, intent=intent)
    catalyst = Catalyst(max_concurrency=1)
    catalyst.add_job(job)
    batch = catalyst.run(research_fn)
    t_research = time.monotonic() - t0

    if not batch.results[0].success:
        raise RuntimeError(f"Research failed: {batch.results[0].error}")

    snapshot = job.research_result["snapshot"]
    print(f"  -> Research complete ({t_research:.1f}s), page_type={snapshot['page_type_recommendation']}")

    # Save research artifact
    (output / "research.json").write_text(json.dumps(snapshot, indent=2))

    # Step 2: Convert to cluster
    print("[2/5] Converting ResearchResult → cluster")
    cluster = research_to_cluster(snapshot)
    print(f"  -> cluster: {json.dumps(cluster, indent=2)}")

    # Step 3: Load pSEO Engine config
    print(f"[3/5] Loading pSEO Engine config: {config_path}")
    config = load_config(config_path)
    print(f"  -> model: {config.generation.model}")

    # Step 4: Generate article via pSEO Engine + LiteLLM + OpenRouter
    print("[4/5] Generating article via pSEO Engine (real LLM call)...")
    t1 = time.monotonic()
    last_err = None
    for attempt in range(5):
        try:
            draft = generate_article(cluster, config, dry_run=False)
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
    t_generate = time.monotonic() - t1
    print(f"  -> Generation complete ({t_generate:.1f}s), status={draft['status']}")

    # Save draft artifact
    (output / "page.json").write_text(json.dumps(draft, indent=2, default=str))

    # Step 5: Render to HTML
    print("[5/5] Rendering structured data → HTML")
    structured = draft.get("structured_data", {})
    template_name = draft.get("template_used", "comparison-guide")
    html_body = render_article(template_name, structured)

    # Wrap in full HTML document
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
</body>
</html>"""

    (output / "page.html").write_text(html_page)
    print(f"  -> Saved: {output / 'page.html'}")

    # Summary
    total = time.monotonic() - t0
    print(f"\nDone. Total time: {total:.1f}s")
    print(f"  Research: {t_research:.1f}s")
    print(f"  Generation: {t_generate:.1f}s")
    print(f"  Artifacts: {output}")

    return {
        "keyword": keyword,
        "template": template_name,
        "status": draft["status"],
        "html_path": str(output / "page.html"),
        "json_path": str(output / "page.json"),
        "research_path": str(output / "research.json"),
        "t_research": t_research,
        "t_generate": t_generate,
        "t_total": total,
        "model": config.generation.model,
    }


if __name__ == "__main__":
    result = run_pipeline(
        keyword="best CRM for textile manufacturers",
        intent="commercial",
        config_path=str(Path(__file__).resolve().parent / "openrouter.yaml"),
        output_dir=str(Path(__file__).resolve().parent / "output"),
    )
    print(json.dumps(result, indent=2))
