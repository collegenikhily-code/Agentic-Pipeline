"""Mapping layer: joins SE Ranking discovery artifacts with crawled competitor content.

Loads discovery outputs (keyword_observations, keyword_clusters, competitor_pages,
page_opportunities) and combines them with crawled page content to produce
IntelligenceRecords ready for Dify ingestion.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .models import IntelligenceRecord, SerankingMeta

logger = logging.getLogger(__name__)


class DiscoveryArtifacts:
    """Container for loaded discovery run artifacts."""

    def __init__(
        self,
        keyword_observations: Optional[list[dict]] = None,
        keyword_clusters: Optional[list[dict]] = None,
        competitor_pages: Optional[list[dict]] = None,
        page_opportunities: Optional[list[dict]] = None,
    ):
        self.keyword_observations = keyword_observations or []
        self.keyword_clusters = keyword_clusters or []
        self.competitor_pages = competitor_pages or []
        self.page_opportunities = page_opportunities or []

    @classmethod
    def load(cls, discovery_dir: str | Path) -> "DiscoveryArtifacts":
        """Load artifacts from a discovery run directory.

        Expects discovery_dir to contain:
            raw/keyword_observations.json
            raw/keyword_clusters.json
            raw/competitor_pages.json
            raw/page_opportunities.json
        """
        discovery_dir = Path(discovery_dir)
        raw_dir = discovery_dir / "raw"

        def _load(name: str) -> list[dict]:
            path = raw_dir / name
            if not path.exists():
                logger.warning(f"Missing discovery artifact: {path}")
                return []
            try:
                data = json.loads(path.read_text())
                return data if isinstance(data, list) else []
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load {path}: {e}")
                return []

        return cls(
            keyword_observations=_load("keyword_observations.json"),
            keyword_clusters=_load("keyword_clusters.json"),
            competitor_pages=_load("competitor_pages.json"),
            page_opportunities=_load("page_opportunities.json"),
        )


class CrawledPageContent:
    """Container for crawled competitor page content."""

    def __init__(self, pages: list[dict]):
        self.pages = pages

    @classmethod
    def load(cls, path: str | Path) -> "CrawledPageContent":
        """Load crawled pages from a JSON file.

        Supports two formats:
        - A list of page dicts (e.g., crawl_results.json)
        - A dict with a "pages" key containing a list
        """
        path = Path(path)
        if not path.exists():
            logger.warning(f"Crawled pages file not found: {path}")
            return cls([])
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return cls(data)
            if isinstance(data, dict):
                pages = data.get("pages", data.get("results", []))
                return cls(pages if isinstance(pages, list) else [])
            return cls([])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load crawled pages from {path}: {e}")
            return cls([])

    def by_url(self) -> dict[str, dict]:
        """Index pages by URL for fast lookup."""
        index = {}
        for page in self.pages:
            url = page.get("url", "")
            if url:
                index[url] = page
        return index


class IntelligenceMapper:
    """Joins SE Ranking discovery data with crawled competitor content.

    Produces IntelligenceRecords that are traceable back to SE Ranking data.
    """

    def __init__(
        self,
        artifacts: DiscoveryArtifacts,
        crawled: Optional[CrawledPageContent] = None,
    ):
        self.artifacts = artifacts
        self.crawled = crawled or CrawledPageContent([])
        self._crawled_by_url = self.crawled.by_url()

        # Build lookup indexes
        self._obs_by_url: dict[str, list[dict]] = {}
        for obs in artifacts.keyword_observations:
            url = obs.get("ranking_url", "")
            if url:
                self._obs_by_url.setdefault(url, []).append(obs)

        self._cluster_by_id: dict[str, dict] = {}
        self._cluster_by_keyword: dict[str, dict] = {}
        for cluster in artifacts.keyword_clusters:
            cid = cluster.get("cluster_id", "")
            if cid:
                self._cluster_by_id[cid] = cluster
            pk = cluster.get("primary_keyword", "")
            if pk:
                self._cluster_by_keyword[pk] = cluster

        self._opp_by_keyword: dict[str, dict] = {}
        for opp in artifacts.page_opportunities:
            pk = opp.get("primary_keyword", "")
            if pk:
                self._opp_by_keyword[pk] = opp

    def _find_cluster_for_url(self, url: str, keyword: str) -> Optional[dict]:
        """Find the keyword cluster that references this URL."""
        for cluster in self.artifacts.keyword_clusters:
            pages = cluster.get("competitor_pages", [])
            if url in pages:
                return cluster
            # Also match by primary keyword
            if cluster.get("primary_keyword", "") == keyword:
                return cluster
        return None

    def _find_opportunity_for_keyword(self, keyword: str) -> Optional[dict]:
        """Find the page opportunity for a keyword."""
        return self._opp_by_keyword.get(keyword)

    def _build_seranking_meta(
        self,
        obs: Optional[dict],
        cluster: Optional[dict],
        opportunity: Optional[dict],
    ) -> SerankingMeta:
        """Build SerankingMeta from the best available sources."""
        keyword = ""
        intent = ""
        search_volume = 0
        difficulty = 0.0
        ranking_position = None
        cluster_id = ""

        if obs:
            keyword = obs.get("keyword", "")
            intent = obs.get("intent", "")
            search_volume = obs.get("search_volume", 0)
            difficulty = obs.get("difficulty", 0.0)
            ranking_position = obs.get("ranking_position")

        if cluster:
            cluster_id = cluster.get("cluster_id", "")
            if not keyword:
                keyword = cluster.get("primary_keyword", "")
            if not intent:
                intent = cluster.get("dominant_intent", "")
            if not search_volume:
                search_volume = cluster.get("total_search_volume", 0)
            if not difficulty:
                difficulty = cluster.get("avg_difficulty", 0.0)

        if opportunity:
            if not keyword:
                keyword = opportunity.get("primary_keyword", "")
            if not intent:
                intent = opportunity.get("intent", "")
            if not search_volume:
                search_volume = opportunity.get("search_volume", 0)
            if not difficulty:
                difficulty = opportunity.get("difficulty", 0.0)

        return SerankingMeta(
            keyword=keyword,
            cluster_id=cluster_id,
            intent=intent,
            search_volume=search_volume,
            difficulty=difficulty,
            ranking_position=ranking_position,
        )

    def map_one(
        self,
        url: str,
        competitor_domain: str,
        title: str = "",
        content: str = "",
        page_type: str = "",
        headings: Optional[list[str]] = None,
        description: str = "",
        faq: Optional[list[dict]] = None,
        word_count: int = 0,
        keyword_hint: str = "",
    ) -> Optional[IntelligenceRecord]:
        """Build a single IntelligenceRecord for a competitor URL.

        Looks up SE Ranking metadata (observations, cluster, opportunity)
        and combines with provided crawled content.
        Returns None if no SE Ranking metadata can be found for this URL.
        """
        # Find SE Ranking observations for this URL
        observations = self._obs_by_url.get(url, [])

        # Determine the primary keyword for this URL
        keyword = keyword_hint
        if not keyword and observations:
            keyword = observations[0].get("keyword", "")
        if not keyword:
            # Check competitor_pages for keyword associations
            for page in self.artifacts.competitor_pages:
                if page.get("url") == url:
                    keywords = page.get("keywords", [])
                    if keywords:
                        keyword = keywords[0]
                        break

        if not keyword and not observations:
            logger.debug(f"No SE Ranking metadata found for URL: {url}")
            return None

        # Find cluster and opportunity
        cluster = self._find_cluster_for_url(url, keyword) if keyword else None
        opportunity = self._find_opportunity_for_keyword(keyword) if keyword else None

        # If we have observations but no primary keyword yet
        if not keyword and observations:
            keyword = observations[0].get("keyword", "")

        # Build seranking metadata
        seranking = self._build_seranking_meta(
            observations[0] if observations else None,
            cluster,
            opportunity,
        )

        # Use crawled content if available
        crawled = self._crawled_by_url.get(url, {})
        if not title:
            title = crawled.get("title", "")
        if not content:
            content = crawled.get("main_content", crawled.get("content", ""))
        if not page_type:
            page_type = crawled.get("page_type", "")
        if not headings:
            headings = crawled.get("headings", [])
        if not description:
            description = crawled.get("description", crawled.get("meta_description", ""))
        if not faq:
            faq = crawled.get("faq", [])
        if not word_count:
            word_count = crawled.get("word_count", 0)

        record = IntelligenceRecord(
            url=url,
            competitor_domain=competitor_domain,
            title=title,
            content=content,
            page_type=page_type,
            seranking=seranking,
            headings=headings or [],
            description=description,
            faq=faq or [],
            word_count=word_count,
        )
        # Preserve crawled content_hash if available (don't recompute)
        crawled_hash = crawled.get("content_hash", "")
        if crawled_hash:
            record.content_hash = crawled_hash
        return record

    def map_all(
        self,
        max_records: Optional[int] = None,
        require_content: bool = False,
    ) -> list[IntelligenceRecord]:
        """Map all competitor URLs from discovery artifacts to IntelligenceRecords.

        Args:
            max_records: Optional cap on number of records produced.
            require_content: If True, skip records without crawled content.

        Returns:
            List of IntelligenceRecords, each traceable to SE Ranking data.
        """
        # Collect all unique URLs from competitor_pages and observations
        url_to_domain: dict[str, str] = {}
        url_to_keyword: dict[str, str] = {}

        for page in self.artifacts.competitor_pages:
            url = page.get("url", "")
            domain = page.get("domain", "")
            if url and domain:
                url_to_domain[url] = domain
                keywords = page.get("keywords", [])
                if keywords:
                    url_to_keyword[url] = keywords[0]

        for obs in self.artifacts.keyword_observations:
            url = obs.get("ranking_url", "")
            domain = obs.get("ranking_domain", "")
            if url and domain and url not in url_to_domain:
                url_to_domain[url] = domain
                keyword = obs.get("keyword", "")
                if keyword:
                    url_to_keyword[url] = keyword

        records = []
        for url, domain in url_to_domain.items():
            keyword = url_to_keyword.get(url, "")

            # Check if we have crawled content
            has_crawled = url in self._crawled_by_url
            if require_content and not has_crawled:
                continue

            record = self.map_one(
                url=url,
                competitor_domain=domain,
                keyword_hint=keyword,
            )
            if record:
                records.append(record)
                if max_records and len(records) >= max_records:
                    break

        logger.info(f"Mapped {len(records)} intelligence records from discovery artifacts")
        return records


def load_crawled_pages_from_proof(proof_dir: str | Path) -> CrawledPageContent:
    """Load crawled pages from an existing competitor proof output directory."""
    proof_dir = Path(proof_dir)
    crawl_file = proof_dir / "crawl_results.json"
    if crawl_file.exists():
        return CrawledPageContent.load(crawl_file)
    return CrawledPageContent([])
