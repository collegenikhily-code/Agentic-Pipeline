"""Lean pipeline: Research → litellm → JSON validate → render → HTML.

Bypasses pSEO Engine's internal retry to control API call rate.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "pseo-engine-oss" / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from seo_aeo_geo_pipeline.models import PageJob
from seo_aeo_geo_pipeline.catalyst import Catalyst, create_research_fn
from seo_aeo_geo_pipeline.research.agents import ResearchAgent

from pseo.config import load_config
from pseo.generate import slugify, _strip_json_fence
from pseo.render import render_article
from pseo.schemas.articles import SCHEMA_REGISTRY

import litellm


def run_pipeline(keyword: str, intent: str, config_path: str, output_dir: str) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    # Step 1: Research
    print(f"[1/5] Researching: {keyword}")
    t0 = time.monotonic()
    agent = ResearchAgent()
    job = PageJob(job_id="slice-001", keyword=keyword, intent=intent)
    catalyst = Catalyst(max_concurrency=1)
    catalyst.add_job(job)
    batch = catalyst.run(create_research_fn(agent))
    t_research = time.monotonic() - t0
    if not batch.results[0].success:
        raise RuntimeError(f"Research failed: {batch.results[0].error}")
    snapshot = job.research_result["snapshot"]
    print(f"  -> Done ({t_research:.1f}s), page_type={snapshot['page_type_recommendation']}")
    (output / "research.json").write_text(json.dumps(snapshot, indent=2))

    # Step 2: Load config + schema
    print("[2/5] Loading config and schema")
    config = load_config(config_path)
    template_name = snapshot.get("page_type_recommendation", "comparison-guide")
    schema_cls = SCHEMA_REGISTRY.get(template_name)
    if schema_cls is None:
        raise ValueError(f"No schema for template: {template_name}")
    print(f"  -> model={config.generation.model}, template={template_name}, schema={schema_cls.__name__}")

    # Step 3: Build prompt and call litellm directly
    print("[3/5] Generating article via litellm/OpenRouter")
    schema_json = json.dumps(schema_cls.model_json_schema(), indent=2)
    prompt = (
        f"You are writing a {template_name} article for a manufacturing industry guide.\n"
        f"Keyword: {keyword}\n"
        f"Intent: {intent}\n\n"
        f"Return your response as a single JSON object matching this schema exactly:\n"
        f"```json\n{schema_json}\n```\n"
        f"Return ONLY valid JSON. No markdown fences, no explanation, no thinking."
    )

    last_err = None
    for attempt in range(8):
        try:
            t1 = time.monotonic()
            response = litellm.completion(
                model=config.generation.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            text = response.choices[0].message.content or ""
            cleaned = _strip_json_fence(text)
            article = schema_cls.model_validate_json(cleaned)
            t_generate = time.monotonic() - t1
            print(f"  -> Generation succeeded ({t_generate:.1f}s, attempt {attempt+1})")
            break
        except Exception as e:
            last_err = e
            wait = 15 * (attempt + 1)
            print(f"  Attempt {attempt+1}/8 failed: {type(e).__name__}: {str(e)[:120]}")
            if attempt < 7:
                print(f"  Waiting {wait}s before retry...")
                time.sleep(wait)
    else:
        raise last_err

    # Step 4: Build draft
    print("[4/5] Building draft")
    slug = slugify(keyword)
    draft = {
        "slug": slug,
        "keyword": keyword,
        "intent": intent,
        "template_used": template_name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "generated",
        "meta_title": f"Best {keyword.title()} - Complete Guide {time.strftime('%Y')}",
        "meta_description": f"Compare the best {keyword} options. Expert analysis and recommendations.",
        "schema_type": type(article).__name__,
        "structured_data": article.model_dump(),
    }
    (output / "page.json").write_text(json.dumps(draft, indent=2, default=str))

    # Step 5: Render to HTML
    print("[5/5] Rendering HTML")
    structured = draft["structured_data"]
    html_body = render_article(template_name, structured)
    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{draft['meta_title']}</title>
<meta name="description" content="{draft['meta_description']}">
</head>
<body>
{html_body}
</body>
</html>"""
    (output / "page.html").write_text(html_page)

    total = time.monotonic() - t0
    print(f"\nDone. Total: {total:.1f}s | Research: {t_research:.1f}s | Generate: {t_generate:.1f}s")
    print(f"Artifacts: {output / 'page.html'}")

    return {
        "keyword": keyword,
        "template": template_name,
        "model": config.generation.model,
        "status": "generated",
        "html_path": str(output / "page.html"),
        "t_total": total,
    }


if __name__ == "__main__":
    result = run_pipeline(
        keyword="best CRM for textile manufacturers",
        intent="commercial",
        config_path=str(Path(__file__).resolve().parent / "openrouter.yaml"),
        output_dir=str(Path(__file__).resolve().parent / "output"),
    )
    print(json.dumps(result, indent=2))
