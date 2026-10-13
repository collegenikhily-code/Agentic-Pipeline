"""Data models for competitor intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class CompetitorConfig:
    """Configuration for a single competitor."""
    name: str
    domain: str
    seed_urls: list[str] = field(default_factory=list)
    enabled: bool = True
    max_pages: int = 10
    priority: int = 0  # higher = crawl first


@dataclass
class CrawlConfig:
    """Global crawl configuration."""
    enabled: bool = False
    max_pages_per_domain: int = 10
    max_depth: int = 2
    request_timeout: int = 15
    max_retries: int = 3
    retry_base_delay: float = 1.0
    global_concurrency: int = 5
    per_domain_concurrency: int = 2
    crawl_delay: float = 1.0
    max_response_bytes: int = 5 * 1024 * 1024  # 5 MB
    user_agent: str = "SEO-AEO-GEO-Pipeline/1.0 (competitive-research)"
    cache_ttl_hours: int = 168  # 7 days
    respect_robots_txt: bool = True
    relevant_path_hints: list[str] = field(default_factory=lambda: [
        "product", "features", "solutions", "use-case", "use_cases",
        "integrations", "pricing", "faq", "docs", "documentation",
        "help", "blog", "guide",
    ])
    exclude_path_hints: list[str] = field(default_factory=lambda: [
        "careers", "login", "signup", "account", "legal",
        "privacy", "cookie", "terms", "assets", "static",
        "cdn", "api", "webhook",
    ])


@dataclass
class CrawledPage:
    """A fetched and extracted competitor page."""
    competitor: str
    domain: str
    url: str
    canonical_url: str = ""
    title: str = ""
    description: str = ""
    page_type: str = "other"
    headings: list[str] = field(default_factory=list)
    main_content: str = ""
    faq: list[dict[str, str]] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    published_date: Optional[str] = None
    modified_date: Optional[str] = None
    word_count: int = 0
    content_hash: str = ""
    crawled_at: str = ""
    http_status: int = 0
    error: Optional[str] = None


@dataclass
class CompetitorEvidence:
    """A single piece of competitor evidence for research."""
    competitor: str
    url: str
    page_type: str
    relevant_content: str
    relevant_headings: list[str] = field(default_factory=list)
    relevant_claims: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    crawled_at: str = ""


@dataclass
class CompetitorResearchPack:
    """Aggregated competitor intelligence for an SEO opportunity."""
    opportunity_keyword: str
    evidence: list[CompetitorEvidence] = field(default_factory=list)
    common_coverage: list[str] = field(default_factory=list)
    competitor_differences: list[dict[str, str]] = field(default_factory=list)
    content_gaps: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    generated_at: str = ""
