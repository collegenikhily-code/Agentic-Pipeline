#!/usr/bin/env python3
"""Prove real research integration with ONE opportunity from Discovery.

Uses "meta ads mcp" opportunity (2810 volume, 5 competitor pages) from the
latest discovery run. This is NOT a mock - it calls a real LLM via litellm.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from seo_aeo_geo_pipeline.research.deep_research import DeepResearchAgent
from seo_aeo_geo_pipeline.research.dify_rag import DifyRAGClient


def main():
    print("=" * 70)
    print("DEEP RESEARCH PROOF - Real Opportunity from Discovery")
    print("=" * 70)

    # Load the real opportunity from discovery output
    opps_path = Path("runs/20260917-125039/discovery/raw/page_opportunities.json")
    if not opps_path.exists():
        print(f"ERROR: Discovery output not found at {opps_path}")
        sys.exit(1)

    opportunities = json.loads(opps_path.read_text())

    # Find "meta ads mcp" - good volume, 5 competitor pages
    target = None
    for opp in opportunities:
        if opp["primary_keyword"] == "meta ads mcp":
            target = opp
            break

    if not target:
        print("ERROR: 'meta ads mcp' opportunity not found")
        sys.exit(1)

    print(f"\nOpportunity: {target['primary_keyword']}")
    print(f"Volume: {target['search_volume']}")
    print(f"Intent: {target['intent']}")
    print(f"Competitor pages: {len(target['competitor_pages'])}")
    print(f"Questions: {len(target.get('questions', []))}")
    print(f"Recommended type: {target['recommended_page_type']}")

    # Initialize agents
    dify = DifyRAGClient()
    print(f"\nDify status: {'configured' if dify.is_configured else 'not configured (graceful fallback)'}")

    agent = DeepResearchAgent(dify_client=dify)
    print(f"LLM model: {agent.model}")

    # Run real research
    print(f"\nRunning deep research on '{target['primary_keyword']}'...")
    start = time.time()

    result = agent.run_full_cycle(
        keyword=target["primary_keyword"],
        intent=target["intent"],
        opportunity_id=1,
        competitor_pages=target.get("competitor_pages", []),
    )

    elapsed = time.time() - start
    print(f"Research completed in {elapsed:.1f}s")

    # Inspect results
    plan = result["plan"]
    dataset = result["dataset"]
    snapshot = result["snapshot"]

    print(f"\n--- Research Plan ---")
    print(f"Sub-questions: {len(plan.sub_questions)}")
    for sq in plan.sub_questions:
        status = "ANSWERED" if sq.answered else "OPEN"
        print(f"  [{status}] {sq.question}")

    print(f"\n--- Research Dataset ---")
    print(f"Sources collected: {len(dataset.sources)}")
    print(f"Questions answered: {len(dataset.questions_answered)}")
    print(f"Content gaps: {len(dataset.content_gaps)}")
    print(f"Page type: {dataset.page_type_recommendation}")
    print(f"Differentiation: {dataset.differentiation_strategy[:100]}...")

    print(f"\n--- Evidence by Claim ---")
    for claim, evidence_list in dataset.evidence_by_claim.items():
        print(f"  Claim: {claim[:60]}...")
        for ev in evidence_list:
            print(f"    Evidence: {ev[:100]}...")

    print(f"\n--- Snapshot ---")
    print(f"Provider: {snapshot['provider']}")
    print(f"Source count: {snapshot['source_count']}")
    print(f"Data hash: {snapshot['data_hash']}")

    # Save results
    output_dir = Path("runs/20260917-125039/research")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Serialize dataclasses
    plan_dict = {
        "primary_keyword": plan.primary_keyword,
        "intent": plan.intent,
        "sub_questions": [{"id": sq.id, "question": sq.question, "intent": sq.intent, "answered": sq.answered} for sq in plan.sub_questions],
        "target_audience": plan.target_audience,
        "content_gaps": plan.content_gaps,
        "competing_pages": plan.competing_pages,
    }
    dataset_dict = {
        "primary_keyword": dataset.primary_keyword,
        "intent": dataset.intent,
        "sources": dataset.sources,
        "evidence_by_claim": dataset.evidence_by_claim,
        "content_gaps": dataset.content_gaps,
        "questions_answered": dataset.questions_answered,
        "audience_profile": dataset.audience_profile,
        "page_type_recommendation": dataset.page_type_recommendation,
        "differentiation_strategy": dataset.differentiation_strategy,
    }

    (output_dir / "research_plan.json").write_text(json.dumps(plan_dict, indent=2))
    (output_dir / "research_dataset.json").write_text(json.dumps(dataset_dict, indent=2))
    (output_dir / "research_snapshot.json").write_text(json.dumps(snapshot, indent=2))

    print(f"\nResults saved to {output_dir}/")
    print("=" * 70)
    print("PROOF COMPLETE - Real research produced from real LLM call")
    print("=" * 70)


if __name__ == "__main__":
    main()
