"""Deterministic page-type classification for competitor pages."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import CrawledPage


# Path-based classification rules (ordered by specificity)
_PATH_RULES: list[tuple[str, list[str]]] = [
    ("pricing", ["pricing", "price", "plans"]),
    ("faq", ["faq", "frequently-asked", "help-center"]),
    ("documentation", ["docs", "documentation", "help", "guide", "learn", "reference"]),
    ("integration", ["integrations", "connect", "sync", "api", "zapier"]),
    ("use_case", ["use-case", "use_case", "solutions", "cases"]),
    ("feature", ["features", "product", "capabilities"]),
    ("blog", ["blog", "articles", "resources", "news"]),
    ("product", ["app", "platform", "dashboard"]),
]


def classify_page(page: CrawledPage) -> str:
    """Classify a crawled page based on URL path, title, and content.

    Returns one of: product, feature, solution, use_case, integration,
    pricing, documentation, faq, blog, other.
    """
    url = page.url.lower()
    parsed = urlparse(url)
    path = parsed.path.lower()
    title = page.title.lower()
    headings_text = " ".join(h.lower() for h in page.headings)

    # Check URL path first (strongest signal)
    for page_type, keywords in _PATH_RULES:
        for kw in keywords:
            if f"/{kw}" in path or path.endswith(f"/{kw}"):
                return page_type

    # Check title
    for page_type, keywords in _PATH_RULES:
        for kw in keywords:
            if kw in title:
                return page_type

    # Check headings
    for page_type, keywords in _PATH_RULES:
        for kw in keywords:
            if kw in headings_text:
                return page_type

    # Root URL is likely product/homepage
    if path in ("", "/"):
        return "product"

    return "other"


def classify_all(pages: list[CrawledPage]) -> list[CrawledPage]:
    """Classify all pages in-place and return the list."""
    for page in pages:
        if not page.error:
            page.page_type = classify_page(page)
    return pages
