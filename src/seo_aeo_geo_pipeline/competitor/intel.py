"""Competitor Intelligence: orchestrates crawl, extract, store, retrieve."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .classifier import classify_all
from .config import load_competitor_config
from .crawler import CompetitorCrawler, _normalize_url
from .extractor import extract_content
from .models import (
    CompetitorConfig,
    CompetitorEvidence,
    CompetitorResearchPack,
    CrawlConfig,
    CrawledPage,
)
from .retriever import retrieve_relevant
from .storage import CompetitorStore

logger = logging.getLogger(__name__)


class CompetitorIntel:
    """Main entry point for competitor intelligence."""

    def __init__(
        self,
        crawl_config: CrawlConfig,
        competitors: list[CompetitorConfig],
        store: CompetitorStore,
    ):
        self.crawl_config = crawl_config
        self.competitors = {c.domain: c for c in competitors if c.enabled}
        self.store = store
        self.crawler = CompetitorCrawler(crawl_config)

    @classmethod
    def from_config(cls, config_path: str | Path | None = None) -> CompetitorIntel:
        """Create from a YAML config file."""
        crawl_config, competitors = load_competitor_config(config_path)
        store_dir = Path(config_path).parent.parent / "data" / "competitor_cache" if config_path else Path("data/competitor_cache")
        store = CompetitorStore(store_dir, crawl_config.cache_ttl_hours)
        return cls(crawl_config, competitors, store)

    def crawl_competitor(self, domain: str, force: bool = False) -> list[CrawledPage]:
        """Crawl a single competitor and return extracted pages."""
        comp = self.competitors.get(domain)
        if not comp:
            logger.warning(f"Unknown competitor: {domain}")
            return []

        logger.info(f"Crawling {domain} (max_pages={comp.max_pages})")

        # Reset crawler state for this domain
        self.crawler.reset()

        # Discover URLs via BFS (this fetches pages to discover links)
        start_url = comp.seed_urls[0] if comp.seed_urls else f"https://{domain}"
        urls = self.crawler.discover_urls(start_url, domain, comp.max_pages)
        logger.info(f"Discovered {len(urls)} URLs for {domain}")

        # Process pages: use cached versions, or the pages already fetched by discover
        pages = []
        for url in urls:
            # Check cache first
            if not force:
                cached = self.store.get(url, domain)
                if cached:
                    pages.append(cached)
                    continue

            # Fetch fresh (skips URLs already in _seen_urls from discover)
            page = self.crawler.fetch_page(url, domain)
            page.competitor = comp.name

            if not page.error:
                page = extract_content(page)
                page.page_type = classify_page_from_page(page)

            pages.append(page)
            self.store.put(page)

        # Classify all
        classify_all(pages)

        success = [p for p in pages if not p.error]
        failed = [p for p in pages if p.error]
        logger.info(f"{domain}: {len(success)} OK, {len(failed)} failed")

        return pages

    def crawl_all(self, force: bool = False) -> dict[str, list[CrawledPage]]:
        """Crawl all enabled competitors."""
        results = {}
        sorted_competitors = sorted(
            self.competitors.values(),
            key=lambda c: -c.priority,
        )
        for comp in sorted_competitors:
            results[comp.domain] = self.crawl_competitor(comp.domain, force=force)
        return results

    def get_all_pages(self) -> list[CrawledPage]:
        """Get all cached pages across all competitors."""
        pages = []
        for domain in self.competitors:
            pages.extend(self.store.get_all(domain))
        return pages

    def build_research_pack(
        self,
        opportunity_keyword: str,
        top_k: int = 10,
    ) -> CompetitorResearchPack:
        """Build a competitor research pack for an SEO opportunity.

        This is the main output: bounded competitor evidence ready
        for injection into Deep Research.
        """
        pages = self.get_all_pages()
        if not pages:
            logger.warning("No cached competitor pages available")
            return CompetitorResearchPack(
                opportunity_keyword=opportunity_keyword,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        # Retrieve relevant evidence
        evidence = retrieve_relevant(pages, opportunity_keyword, top_k=top_k)

        # Analyze coverage patterns
        common, differences, gaps = self._analyze_coverage(evidence, opportunity_keyword)

        source_urls = list({e.url for e in evidence})

        pack = CompetitorResearchPack(
            opportunity_keyword=opportunity_keyword,
            evidence=evidence,
            common_coverage=common,
            competitor_differences=differences,
            content_gaps=gaps,
            source_urls=source_urls,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            f"Research pack for '{opportunity_keyword}': "
            f"{len(evidence)} evidence items, "
            f"{len(common)} common topics, "
            f"{len(gaps)} potential gaps"
        )

        return pack

    def _analyze_coverage(
        self,
        evidence: list[CompetitorEvidence],
        query: str,
    ) -> tuple[list[str], list[dict[str, str]], list[str]]:
        """Analyze competitor coverage patterns."""
        query_words = set(query.lower().split())

        # Count which topics competitors cover
        topic_competitors: dict[str, set[str]] = {}
        for e in evidence:
            words = set(e.relevant_content.lower().split())
            for word in query_words:
                if word in words:
                    topic_competitors.setdefault(word, set()).add(e.competitor)

        # Common: topics covered by 2+ competitors
        common = []
        for topic, comps in topic_competitors.items():
            if len(comps) >= 2:
                common.append(f"{topic} (covered by {', '.join(comps)})")

        # Differences: unique claims per competitor
        differences = []
        competitor_claims: dict[str, list[str]] = {}
        for e in evidence:
            competitor_claims.setdefault(e.competitor, []).extend(e.relevant_claims)

        for comp, claims in competitor_claims.items():
            if claims:
                differences.append({
                    "competitor": comp,
                    "unique_emphasis": claims[0][:200] if claims else "",
                })

        # Gaps: topics in query but not well-covered
        gaps = []
        for topic in query_words:
            if topic not in topic_competitors or len(topic_competitors[topic]) < 2:
                gaps.append(f"'{topic}' — not widely observed in crawled corpus")

        return common, differences, gaps


@dataclass
class CompetitorIntelReadiness:
    """Readiness assessment for competitor intelligence."""
    total_competitors_configured: int
    total_competitors_crawled: int
    total_urls_discovered: int
    total_pages_crawled: int
    total_pages_successful: int
    total_pages_failed: int
    total_evidence_items: int
    unique_source_urls: int
    cache_hit_rate: float
    is_ready: bool
    blocking_issues: list[str]
    warnings: list[str]


class CompetitorIntel:
    """Main entry point for competitor intelligence."""

    def __init__(
        self,
        crawl_config: CrawlConfig,
        competitors: list[CompetitorConfig],
        store: CompetitorStore,
    ):
        self.crawl_config = crawl_config
        self.competitors = {c.domain: c for c in competitors if c.enabled}
        self.store = store
        self.crawler = CompetitorCrawler(crawl_config)
        self._crawl_stats: dict[str, dict] = {}

    @classmethod
    def from_config(cls, config_path: str | Path | None = None) -> CompetitorIntel:
        """Create from a YAML config file."""
        crawl_config, competitors = load_competitor_config(config_path)
        store_dir = Path(config_path).parent.parent / "data" / "competitor_cache" if config_path else Path("data/competitor_cache")
        store = CompetitorStore(store_dir, crawl_config.cache_ttl_hours)
        return cls(crawl_config, competitors, store)

    def crawl_competitor(self, domain: str, force: bool = False) -> list[CrawledPage]:
        """Crawl a single competitor and return extracted pages."""
        comp = self.competitors.get(domain)
        if not comp:
            logger.warning(f"Unknown competitor: {domain}")
            return []

        logger.info(f"Crawling {domain} (max_pages={comp.max_pages})")

        # Reset crawler state for this domain
        self.crawler.reset()

        # Discover URLs via BFS (this fetches pages to discover links)
        start_url = comp.seed_urls[0] if comp.seed_urls else f"https://{domain}"
        urls = self.crawler.discover_urls(start_url, domain, comp.max_pages)
        logger.info(f"Discovered {len(urls)} URLs for {domain}")

        # Process pages: use cached versions, or the pages already fetched by discover
        pages = []
        cached_count = 0
        fetched_count = 0
        for url in urls:
            # Check cache first
            if not force:
                cached = self.store.get(url, domain)
                if cached:
                    pages.append(cached)
                    cached_count += 1
                    continue

            # Fetch fresh (skips URLs already in _seen_urls from discover)
            page = self.crawler.fetch_page(url, domain)
            page.competitor = comp.name

            if not page.error:
                page = extract_content(page)
                page.page_type = classify_page_from_page(page)

            pages.append(page)
            self.store.put(page)
            fetched_count += 1

        # Classify all
        classify_all(pages)

        success = [p for p in pages if not p.error]
        failed = [p for p in pages if p.error]
        logger.info(f"{domain}: {len(success)} OK, {len(failed)} failed, {cached_count} cached, {fetched_count} fetched")

        # Store stats
        self._crawl_stats[domain] = {
            "urls_discovered": len(urls),
            "pages_crawled": len(pages),
            "successful": len(success),
            "failed": len(failed),
            "cached": cached_count,
            "fetched": fetched_count,
        }

        return pages

    def crawl_all(self, force: bool = False) -> dict[str, list[CrawledPage]]:
        """Crawl all enabled competitors."""
        results = {}
        sorted_competitors = sorted(
            self.competitors.values(),
            key=lambda c: -c.priority,
        )
        for comp in sorted_competitors:
            results[comp.domain] = self.crawl_competitor(comp.domain, force=force)
        return results

    def get_all_pages(self) -> list[CrawledPage]:
        """Get all cached pages across all competitors."""
        pages = []
        for domain in self.competitors:
            pages.extend(self.store.get_all(domain))
        return pages

    def get_readiness(self, opportunity_keyword: str | None = None) -> CompetitorIntelReadiness:
        """Assess competitor intelligence readiness for research.

        Returns a detailed readiness report including coverage metrics,
        evidence quality, and blocking issues.
        """
        pages = self.get_all_pages()

        total_competitors_configured = len(self.competitors)
        total_competitors_crawled = len(set(p.competitor for p in pages))
        all_urls_discovered = sum(s.get("urls_discovered", 0) for s in self._crawl_stats.values())
        total_pages_crawled = len(pages)
        total_pages_successful = len([p for p in pages if not p.error])
        total_pages_failed = len([p for p in pages if p.error])
        total_evidence_items = 0
        unique_source_urls = len(set(p.url for p in pages))

        # Calculate cache hit rate
        total_cached = sum(s.get("cached", 0) for s in self._crawl_stats.values())
        total_fetched = sum(s.get("fetched", 0) for s in self._crawl_stats.values())
        total_attempts = total_cached + total_fetched
        cache_hit_rate = total_cached / total_attempts if total_attempts > 0 else 0.0

        blocking_issues = []
        warnings = []

        if total_competitors_crawled == 0:
            blocking_issues.append("No competitors have been crawled")
        elif total_competitors_crawled < total_competitors_configured:
            missing = total_competitors_configured - total_competitors_crawled
            warnings.append(f"{missing} configured competitors not crawled")

        if total_pages_successful == 0:
            blocking_issues.append("No successful page crawls")
        elif total_pages_failed > total_pages_successful:
            warnings.append(f"More failed crawls ({total_pages_failed}) than successful ({total_pages_successful})")

        # Check evidence quality if opportunity keyword provided
        if opportunity_keyword:
            from .retriever import retrieve_relevant
            evidence = retrieve_relevant(pages, opportunity_keyword, top_k=10)
            total_evidence_items = len(evidence)
            if total_evidence_items == 0:
                blocking_issues.append(f"No relevant evidence found for keyword: {opportunity_keyword}")
            elif total_evidence_items < 3:
                warnings.append(f"Low evidence count ({total_evidence_items}) for keyword: {opportunity_keyword}")

        is_ready = len(blocking_issues) == 0

        return CompetitorIntelReadiness(
            total_competitors_configured=total_competitors_configured,
            total_competitors_crawled=total_competitors_crawled,
            total_urls_discovered=all_urls_discovered,
            total_pages_crawled=total_pages_crawled,
            total_pages_successful=total_pages_successful,
            total_pages_failed=total_pages_failed,
            total_evidence_items=total_evidence_items,
            unique_source_urls=unique_source_urls,
            cache_hit_rate=cache_hit_rate,
            is_ready=is_ready,
            blocking_issues=blocking_issues,
            warnings=warnings,
        )

    def _analyze_coverage(
        self,
        evidence: list[CompetitorEvidence],
        query: str,
    ) -> tuple[list[str], list[dict[str, str]], list[str]]:
        """Analyze competitor coverage patterns."""
        query_words = set(query.lower().split())

        # Count which topics competitors cover
        topic_competitors: dict[str, set[str]] = {}
        for e in evidence:
            words = set(e.relevant_content.lower().split())
            for word in query_words:
                if word in words:
                    topic_competitors.setdefault(word, set()).add(e.competitor)

        # Common: topics covered by 2+ competitors
        common = []
        for topic, comps in topic_competitors.items():
            if len(comps) >= 2:
                common.append(f"{topic} (covered by {', '.join(comps)})")

        # Differences: unique claims per competitor
        differences = []
        competitor_claims: dict[str, list[str]] = {}
        for e in evidence:
            competitor_claims.setdefault(e.competitor, []).extend(e.relevant_claims)

        for comp, claims in competitor_claims.items():
            if claims:
                differences.append({
                    "competitor": comp,
                    "unique_emphasis": claims[0][:200] if claims else "",
                })

        # Gaps: topics in query but not well-covered
        gaps = []
        for topic in query_words:
            if topic not in topic_competitors or len(topic_competitors[topic]) < 2:
                gaps.append(f"'{topic}' — not widely observed in crawled corpus")

        return common, differences, gaps

    def build_research_pack(
        self,
        opportunity_keyword: str,
        top_k: int = 10,
    ) -> CompetitorResearchPack:
        """Build a competitor research pack for an SEO opportunity.

        This is the main output: bounded competitor evidence ready
        for injection into Deep Research.
        """
        pages = self.get_all_pages()
        if not pages:
            logger.warning("No cached competitor pages available")
            return CompetitorResearchPack(
                opportunity_keyword=opportunity_keyword,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        # Retrieve relevant evidence
        evidence = retrieve_relevant(pages, opportunity_keyword, top_k=top_k)

        # Analyze coverage patterns
        common, differences, gaps = self._analyze_coverage(evidence, opportunity_keyword)

        source_urls = list({e.url for e in evidence})

        pack = CompetitorResearchPack(
            opportunity_keyword=opportunity_keyword,
            evidence=evidence,
            common_coverage=common,
            competitor_differences=differences,
            content_gaps=gaps,
            source_urls=source_urls,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            f"Research pack for '{opportunity_keyword}': "
            f"{len(evidence)} evidence items, "
            f"{len(common)} common topics, "
            f"{len(gaps)} potential gaps"
        )

        return pack


def classify_page_from_page(page: CrawledPage) -> str:
    """Classify a page (import from classifier module)."""
    from .classifier import classify_page
    return classify_page(page)
