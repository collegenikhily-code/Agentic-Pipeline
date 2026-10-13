#!/usr/bin/env python3
"""Run the Discovery → Mapping → Opportunity pipeline.

Two modes:

  Competitor-led (no own domain):
    python scripts/discover_opportunities.py \
        --competitor adspirer.com \
        --competitor get-ryze.ai \
        --competitor soku.ai \
        --limit 30

  Domain-gap (own domain + competitors):
    python scripts/discover_opportunities.py \
        --domain ourdomain.com \
        --competitor adspirer.com \
        --limit 30

Requires:
    SE_RANKING_API_KEY environment variable
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from seo_aeo_geo_pipeline.discovery.clustering import cluster_keywords
from seo_aeo_geo_pipeline.discovery.models import (
    CompetitorPage,
    KeywordCluster,
    KeywordObservation,
    PageOpportunity,
)
from seo_aeo_geo_pipeline.discovery.normalizer import (
    build_competitor_pages,
    normalize_keywords_response,
    normalize_overlap_response,
    normalize_question_keywords,
    normalize_related_keywords,
)
from seo_aeo_geo_pipeline.discovery.opportunity import clusters_to_opportunities
from seo_aeo_geo_pipeline.discovery.se_ranking import (
    SERankingClient,
    SERankingAuthError,
    SERankingError,
)


def _save_json(data: list | dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def _to_dicts(items: list) -> list[dict]:
    return [item.to_dict() for item in items]


def run_discovery(
    domain: str | None = None,
    competitors: list[str] | None = None,
    source: str = "us",
    keyword_limit: int = 50,
    question_limit: int = 10,
) -> dict:
    """Execute the discovery pipeline.

    Modes:
      - Competitor-led: domain=None, competitors=[...]
      - Domain-gap: domain="...", competitors=[...]
    """
    competitors = competitors or []
    is_competitor_led = domain is None

    if not competitors:
        raise ValueError("At least one --competitor is required.")

    run_id = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(f"runs/{run_id}/discovery")
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    steps_total = 7 if is_competitor_led else 10
    step = 0

    def _step(msg: str) -> None:
        nonlocal step
        step += 1
        print(f"[{step}/{steps_total}] {msg}")

    # --- Step 1: Auth ---
    _step("Authenticating with SE Ranking...")
    client = SERankingClient()
    try:
        sub = client.test_auth()
        print(f"  -> Auth OK. Account: {sub.get('login', 'unknown')}")
    except SERankingAuthError as e:
        print(f"  -> Auth FAILED: {e}")
        return {"status": "auth_failed", "error": str(e)}
    except SERankingError as e:
        print(f"  -> Connection error: {e}")
        return {"status": "connection_error", "error": str(e)}

    # --- Competitor-led mode ---
    if is_competitor_led:
        return _run_competitor_led(
            client=client,
            competitors=competitors,
            source=source,
            keyword_limit=keyword_limit,
            question_limit=question_limit,
            raw_dir=raw_dir,
            output_dir=output_dir,
            run_id=run_id,
            _step=_step,
        )

    # --- Domain-gap mode (original) ---
    return _run_domain_gap(
        client=client,
        domain=domain,
        competitors=competitors,
        source=source,
        keyword_limit=keyword_limit,
        question_limit=question_limit,
        raw_dir=raw_dir,
        output_dir=output_dir,
        run_id=run_id,
        _step=_step,
    )


def _run_competitor_led(
    client: SERankingClient,
    competitors: list[str],
    source: str,
    keyword_limit: int,
    question_limit: int,
    raw_dir: Path,
    output_dir: Path,
    run_id: str,
    _step,
) -> dict:
    """Competitor-led discovery: no own domain, no gap analysis."""

    # --- Step 2: Retrieve keywords for each competitor (paginated) ---
    _step(f"Retrieving keywords for {len(competitors)} competitors (target {keyword_limit}/competitor)...")
    all_observations: list[KeywordObservation] = []
    for comp in competitors:
        try:
            raw_kw = client.get_domain_keywords_all(
                domain=comp, source=source, target_count=keyword_limit
            )
            _save_json(raw_kw, raw_dir / f"keywords_{comp.replace('.', '_')}.json")
            obs = normalize_keywords_response(raw_kw, source_domain=comp)
            all_observations.extend(obs)
            print(f"  -> {len(obs)} keywords for {comp} ({len(raw_kw)} raw records)")
        except SERankingError as e:
            print(f"  -> Keyword retrieval failed for {comp}: {e}")

    # --- Step 3: Normalize ---
    _step("Normalizing data...")
    _save_json(_to_dicts(all_observations), raw_dir / "keyword_observations.json")
    competitor_pages = build_competitor_pages(all_observations)
    _save_json(_to_dicts(competitor_pages), raw_dir / "competitor_pages.json")
    print(f"  -> {len(all_observations)} total keyword observations")
    print(f"  -> {len(competitor_pages)} unique competitor pages")

    # --- Step 4: Cluster ---
    _step("Clustering keywords...")
    clusters = cluster_keywords(all_observations)
    _save_json(_to_dicts(clusters), raw_dir / "keyword_clusters.json")
    print(f"  -> {len(clusters)} keyword clusters")

    # --- Step 5: Questions for top clusters ---
    _step("Retrieving question keywords for top clusters...")
    for cluster in clusters[:5]:
        try:
            raw_q = client.get_question_keywords(
                cluster.primary_keyword, source=source, limit=question_limit
            )
            _save_json(raw_q, raw_dir / f"questions_{cluster.cluster_id[:30]}.json")
            questions = normalize_question_keywords(raw_q)
            cluster.supporting_questions = [
                q.keyword for q in questions if q.keyword
            ]
            print(f"  -> {len(cluster.supporting_questions)} questions for '{cluster.primary_keyword}'")
        except SERankingError as e:
            print(f"  -> Question retrieval failed for '{cluster.primary_keyword}': {e}")

    # --- Step 6: Generate opportunities ---
    _step("Generating page opportunities...")
    opportunities = clusters_to_opportunities(clusters, all_observations)
    _save_json(_to_dicts(opportunities), raw_dir / "page_opportunities.json")
    print(f"  -> {len(opportunities)} page opportunities")

    # --- Step 7: Save report ---
    _step("Saving discovery report...")
    report = {
        "run_id": run_id,
        "mode": "competitor_led",
        "domain": None,
        "competitors": competitors,
        "source": source,
        "total_observations": len(all_observations),
        "total_competitor_pages": len(competitor_pages),
        "total_clusters": len(clusters),
        "total_opportunities": len(opportunities),
        "total_questions": sum(len(c.supporting_questions) for c in clusters),
        "keyword_limit": keyword_limit,
        "output_dir": str(output_dir),
    }
    _save_json(report, output_dir / "discovery_report.json")
    print(f"\nDone. Artifacts saved to: {output_dir}")
    print(f"  Observations: {report['total_observations']}")
    print(f"  Competitor pages: {report['total_competitor_pages']}")
    print(f"  Clusters: {report['total_clusters']}")
    print(f"  Opportunities: {report['total_opportunities']}")
    print(f"  Questions: {report['total_questions']}")
    return report


def _run_domain_gap(
    client: SERankingClient,
    domain: str,
    competitors: list[str],
    source: str,
    keyword_limit: int,
    question_limit: int,
    raw_dir: Path,
    output_dir: Path,
    run_id: str,
    _step,
) -> dict:
    """Domain-gap discovery: own domain + competitors."""

    # --- Step 2: Discover competitors if not provided ---
    if not competitors:
        _step(f"Discovering competitors for {domain}...")
        try:
            raw_comp = client.get_domain_competitors(domain, source=source, limit=10)
            _save_json(raw_comp, raw_dir / "competitors.json")
            if isinstance(raw_comp, dict):
                comp_list = raw_comp.get("competitors") or raw_comp.get("result") or []
            elif isinstance(raw_comp, list):
                comp_list = raw_comp
            else:
                comp_list = []
            competitors = [
                c.get("domain") or c.get("competitor") or c.get("base_domain", "")
                for c in comp_list
                if isinstance(c, dict)
            ]
            competitors = [c for c in competitors if c and c != domain][:5]
            print(f"  -> Found {len(competitors)} competitors: {competitors}")
        except SERankingError as e:
            print(f"  -> Competitor discovery failed: {e}")
            competitors = []
    else:
        _step(f"Using provided competitors: {competitors}")

    # --- Step 3: Our domain keywords (paginated) ---
    _step(f"Retrieving keywords for {domain} (target {keyword_limit})...")
    our_observations: list[KeywordObservation] = []
    try:
        raw_kw = client.get_domain_keywords_all(
            domain=domain, source=source, target_count=keyword_limit
        )
        _save_json(raw_kw, raw_dir / "keywords_ours.json")
        our_observations = normalize_keywords_response(raw_kw, source_domain=domain)
        print(f"  -> {len(our_observations)} keywords for our domain")
    except SERankingError as e:
        print(f"  -> Our keyword retrieval failed: {e}")

    # --- Step 4: Competitor keywords (paginated) ---
    _step("Retrieving competitor keywords...")
    comp_observations: list[KeywordObservation] = []
    for comp in competitors[:3]:
        try:
            raw_comp_kw = client.get_domain_keywords_all(
                domain=comp, source=source, target_count=keyword_limit
            )
            _save_json(raw_comp_kw, raw_dir / f"keywords_{comp.replace('.', '_')}.json")
            obs = normalize_keywords_response(raw_comp_kw, source_domain=comp)
            comp_observations.extend(obs)
            print(f"  -> {len(obs)} keywords for {comp}")
        except SERankingError as e:
            print(f"  -> Keyword retrieval failed for {comp}: {e}")

    all_observations = our_observations + comp_observations

    # --- Step 5: Gap analysis ---
    _step("Analyzing keyword gaps...")
    gap_observations: list[KeywordObservation] = []
    for comp in competitors[:3]:
        try:
            raw_overlap = client.get_keyword_overlap(
                domain1=domain, domain2=comp, source=source
            )
            _save_json(raw_overlap, raw_dir / f"overlap_{comp.replace('.', '_')}.json")
            overlap = normalize_overlap_response(
                raw_overlap, our_domain=domain, competitor_domain=comp
            )
            gap_observations.extend(overlap.get("only_competitor", []))
            print(f"  -> {len(overlap.get('only_competitor', []))} gap keywords vs {comp}")
        except SERankingError as e:
            print(f"  -> Overlap retrieval failed for {comp}: {e}")

    all_observations.extend(gap_observations)

    # --- Step 6: Normalize ---
    _step("Normalizing data...")
    _save_json(_to_dicts(all_observations), raw_dir / "keyword_observations.json")
    competitor_pages = build_competitor_pages(all_observations)
    _save_json(_to_dicts(competitor_pages), raw_dir / "competitor_pages.json")
    print(f"  -> {len(all_observations)} total keyword observations")
    print(f"  -> {len(competitor_pages)} unique competitor pages")

    # --- Step 7: Cluster ---
    _step("Clustering keywords...")
    clusters = cluster_keywords(all_observations)
    _save_json(_to_dicts(clusters), raw_dir / "keyword_clusters.json")
    print(f"  -> {len(clusters)} keyword clusters")

    # --- Step 8: Questions ---
    _step("Retrieving question keywords for top clusters...")
    for cluster in clusters[:5]:
        try:
            raw_q = client.get_question_keywords(
                cluster.primary_keyword, source=source, limit=question_limit
            )
            _save_json(raw_q, raw_dir / f"questions_{cluster.cluster_id[:30]}.json")
            questions = normalize_question_keywords(raw_q)
            cluster.supporting_questions = [
                q.keyword for q in questions if q.keyword
            ]
            print(f"  -> {len(cluster.supporting_questions)} questions for '{cluster.primary_keyword}'")
        except SERankingError as e:
            print(f"  -> Question retrieval failed for '{cluster.primary_keyword}': {e}")

    # --- Step 9: Opportunities ---
    _step("Generating page opportunities...")
    opportunities = clusters_to_opportunities(clusters, all_observations)
    _save_json(_to_dicts(opportunities), raw_dir / "page_opportunities.json")
    print(f"  -> {len(opportunities)} page opportunities")

    # --- Step 10: Report ---
    _step("Saving discovery report...")
    report = {
        "run_id": run_id,
        "mode": "domain_gap",
        "domain": domain,
        "competitors": competitors,
        "source": source,
        "total_observations": len(all_observations),
        "total_competitor_pages": len(competitor_pages),
        "total_clusters": len(clusters),
        "total_opportunities": len(opportunities),
        "total_questions": sum(len(c.supporting_questions) for c in clusters),
        "keyword_limit": keyword_limit,
        "output_dir": str(output_dir),
    }
    _save_json(report, output_dir / "discovery_report.json")
    print(f"\nDone. Artifacts saved to: {output_dir}")
    print(f"  Observations: {report['total_observations']}")
    print(f"  Competitor pages: {report['total_competitor_pages']}")
    print(f"  Clusters: {report['total_clusters']}")
    print(f"  Opportunities: {report['total_opportunities']}")
    print(f"  Questions: {report['total_questions']}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run SEO/AEO/GEO discovery pipeline"
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Our target domain (omit for competitor-led discovery)",
    )
    parser.add_argument(
        "--competitor",
        action="append",
        default=[],
        help="Competitor domain (repeatable, at least one required)",
    )
    parser.add_argument("--source", default="us", help="SE Ranking region code")
    parser.add_argument("--limit", type=int, default=50, help="Keywords per domain")
    parser.add_argument("--question-limit", type=int, default=10, help="Questions per cluster")
    args = parser.parse_args()

    if not args.competitor:
        parser.error("At least one --competitor is required.")

    run_discovery(
        domain=args.domain,
        competitors=args.competitor,
        source=args.source,
        keyword_limit=args.limit,
        question_limit=args.question_limit,
    )


if __name__ == "__main__":
    main()
