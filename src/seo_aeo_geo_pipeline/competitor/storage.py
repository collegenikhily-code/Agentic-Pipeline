"""File-based storage and cache for competitor pages."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from .models import CrawledPage

logger = logging.getLogger(__name__)


class CompetitorStore:
    """File-based storage for crawled competitor pages.

    Directory structure:
        store_dir/
            {domain}/
                {content_hash}.json   -- page data
                _index.json           -- URL -> hash mapping
    """

    def __init__(self, store_dir: str | Path, cache_ttl_hours: int = 168):
        self.store_dir = Path(store_dir)
        self.cache_ttl_seconds = cache_ttl_hours * 3600
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _domain_dir(self, domain: str) -> Path:
        d = self.store_dir / domain
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _index_path(self, domain: str) -> Path:
        return self._domain_dir(domain) / "_index.json"

    def _load_index(self, domain: str) -> dict[str, dict]:
        """Load URL -> {hash, timestamp} mapping."""
        path = self._index_path(domain)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self, domain: str, index: dict[str, dict]) -> None:
        path = self._index_path(domain)
        path.write_text(json.dumps(index, indent=2))

    def get(self, url: str, domain: str) -> Optional[CrawledPage]:
        """Retrieve a cached page if it exists and hasn't expired."""
        index = self._load_index(domain)
        entry = index.get(url)
        if not entry:
            return None

        # Check TTL
        age = time.time() - entry.get("timestamp", 0)
        if age > self.cache_ttl_seconds:
            return None

        content_hash = entry.get("hash", "")
        page_path = self._domain_dir(domain) / f"{content_hash}.json"
        if not page_path.exists():
            return None

        try:
            data = json.loads(page_path.read_text())
            return CrawledPage(**data)
        except (json.JSONDecodeError, TypeError, OSError):
            return None

    def put(self, page: CrawledPage) -> None:
        """Store a crawled page."""
        if not page.domain or not page.url:
            return

        index = self._load_index(page.domain)
        page_dict = _page_to_dict(page)
        page_json = json.dumps(page_dict, indent=2)

        # Write page file
        content_hash = page.content_hash or hashlib.sha256(page.url.encode()).hexdigest()[:16]
        page_path = self._domain_dir(page.domain) / f"{content_hash}.json"
        page_path.write_text(page_json)

        # Update index
        index[page.url] = {
            "hash": content_hash,
            "timestamp": time.time(),
            "http_status": page.http_status,
            "error": page.error,
        }
        self._save_index(page.domain, index)

    def has(self, url: str, domain: str) -> bool:
        """Check if a URL is cached and not expired."""
        return self.get(url, domain) is not None

    def list_pages(self, domain: str) -> list[str]:
        """List all cached URLs for a domain."""
        index = self._load_index(domain)
        return list(index.keys())

    def get_all(self, domain: str) -> list[CrawledPage]:
        """Get all cached pages for a domain."""
        index = self._load_index(domain)
        pages = []
        for url in index:
            page = self.get(url, domain)
            if page:
                pages.append(page)
        return pages

    def stats(self) -> dict[str, int]:
        """Return per-domain page counts."""
        stats = {}
        if self.store_dir.exists():
            for d in self.store_dir.iterdir():
                if d.is_dir() and (d / "_index.json").exists():
                    index = self._load_index(d.name)
                    stats[d.name] = len(index)
        return stats


def _page_to_dict(page: CrawledPage) -> dict:
    """Convert CrawledPage to a JSON-serializable dict."""
    return {
        "competitor": page.competitor,
        "domain": page.domain,
        "url": page.url,
        "canonical_url": page.canonical_url,
        "title": page.title,
        "description": page.description,
        "page_type": page.page_type,
        "headings": page.headings,
        "main_content": page.main_content,
        "faq": page.faq,
        "links": page.links,
        "published_date": page.published_date,
        "modified_date": page.modified_date,
        "word_count": page.word_count,
        "content_hash": page.content_hash,
        "crawled_at": page.crawled_at,
        "http_status": page.http_status,
        "error": page.error,
    }


# Needed for has() method
import hashlib
