"""Competitor intelligence configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import CompetitorConfig, CrawlConfig

_DEFAULT_RELEVANT_PATHS = [
    "product", "features", "solutions", "use-case", "use_cases",
    "integrations", "pricing", "faq", "docs", "documentation",
    "help", "blog", "guide",
]

_DEFAULT_EXCLUDE_PATHS = [
    "careers", "login", "signup", "account", "legal",
    "privacy", "cookie", "terms", "assets", "static",
    "cdn", "api", "webhook",
]


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "competitors.yaml"


def load_competitor_config(path: str | Path | None = None) -> tuple[CrawlConfig, list[CompetitorConfig]]:
    """Load crawl config and competitor list from YAML."""
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return CrawlConfig(), []

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    crawl_raw = raw.get("crawl", {})
    crawl = CrawlConfig(
        enabled=crawl_raw.get("enabled", False),
        max_pages_per_domain=crawl_raw.get("max_pages_per_domain", 10),
        max_depth=crawl_raw.get("max_depth", 2),
        request_timeout=crawl_raw.get("request_timeout", 15),
        max_retries=crawl_raw.get("max_retries", 3),
        retry_base_delay=crawl_raw.get("retry_base_delay", 1.0),
        global_concurrency=crawl_raw.get("global_concurrency", 5),
        per_domain_concurrency=crawl_raw.get("per_domain_concurrency", 2),
        crawl_delay=crawl_raw.get("crawl_delay", 1.0),
        max_response_bytes=crawl_raw.get("max_response_bytes", 5 * 1024 * 1024),
        user_agent=crawl_raw.get("user_agent", "SEO-AEO-GEO-Pipeline/1.0 (competitive-research)"),
        cache_ttl_hours=crawl_raw.get("cache_ttl_hours", 168),
        respect_robots_txt=crawl_raw.get("respect_robots_txt", True),
        relevant_path_hints=crawl_raw.get("relevant_path_hints", _DEFAULT_RELEVANT_PATHS),
        exclude_path_hints=crawl_raw.get("exclude_path_hints", _DEFAULT_EXCLUDE_PATHS),
    )

    competitors = []
    for c in raw.get("competitors", []):
        competitors.append(CompetitorConfig(
            name=c.get("name", ""),
            domain=c.get("domain", ""),
            seed_urls=c.get("seed_urls", []),
            enabled=c.get("enabled", True),
            max_pages=c.get("max_pages", crawl.max_pages_per_domain),
            priority=c.get("priority", 0),
        ))

    return crawl, competitors
