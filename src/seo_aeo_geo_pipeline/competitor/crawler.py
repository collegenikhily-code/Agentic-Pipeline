"""HTTP crawler with retries, robots.txt, rate limiting, and dedup."""

from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import CrawlConfig, CrawledPage

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """Normalize a URL: strip fragment, normalize scheme, remove trailing slash."""
    parsed = urlparse(url)
    # Strip fragment
    fragmentless = parsed._replace(fragment="")
    # Normalize scheme
    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    # Normalize host
    host = parsed.hostname.lower() if parsed.hostname else ""
    # Rebuild without fragment, normalize path
    path = parsed.path or "/"
    # Remove trailing slash for non-root paths
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = f"{scheme}://{host}{path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def _content_hash(text: str) -> str:
    """SHA-256 hash of content for dedup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _is_relevant_url(url: str, config: CrawlConfig) -> bool:
    """Check if URL path matches relevant hints and not excluded hints."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    for hint in config.exclude_path_hints:
        if f"/{hint}" in path or path.startswith(f"/{hint}"):
            return False

    # If no relevant hints specified, allow all non-excluded
    if not config.relevant_path_hints:
        return True

    # Root URL is always relevant
    if path == "/" or path == "":
        return True

    for hint in config.relevant_path_hints:
        if hint in path:
            return True

    return False


class RobotsCache:
    """Minimal robots.txt cache and checker."""

    def __init__(self, user_agent: str, cache_ttl: int = 3600):
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, dict[str, list[str]]]] = {}
        self._session = requests.Session()

    def _fetch(self, domain: str) -> dict[str, list[str]]:
        """Fetch and parse robots.txt for a domain."""
        url = f"https://{domain}/robots.txt"
        try:
            resp = self._session.get(url, timeout=10)
            if resp.status_code != 200:
                return {}
            return self._parse(resp.text)
        except Exception:
            return {}

    def _parse(self, text: str) -> dict[str, list[str]]:
        """Parse robots.txt into a dict of agent -> disallowed paths."""
        rules: dict[str, list[str]] = defaultdict(list)
        current_agent = "*"
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("user-agent:"):
                current_agent = line.split(":", 1)[1].strip()
            elif line.lower().startswith("disallow:"):
                path = line.split(":", 1)[1].strip()
                if path:
                    rules[current_agent].append(path)
        return dict(rules)

    def is_allowed(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        parsed = urlparse(url)
        domain = parsed.hostname
        if not domain:
            return True

        now = time.time()
        if domain in self._cache:
            cached_at, rules = self._cache[domain]
            if now - cached_at < self.cache_ttl:
                return self._check_rules(url, rules)
            del self._cache[domain]

        rules = self._fetch(domain)
        self._cache[domain] = (now, rules)
        return self._check_rules(url, rules)

    def _check_rules(self, url: str, rules: dict[str, list[str]]) -> bool:
        """Check if a URL is disallowed by any matching rule."""
        parsed = urlparse(url)
        path = parsed.path

        # Check specific user-agent first, then wildcard
        for agent in [self.user_agent, "*"]:
            if agent in rules:
                for disallowed in rules[agent]:
                    if path.startswith(disallowed):
                        return False
        return True


class CompetitorCrawler:
    """Controlled crawler for competitor websites."""

    def __init__(self, config: CrawlConfig):
        self.config = config
        self._session = self._build_session()
        self._robots = RobotsCache(config.user_agent) if config.respect_robots_txt else None
        self._seen_urls: set[str] = set()
        self._domain_timestamps: dict[str, float] = defaultdict(float)

    def _build_session(self) -> requests.Session:
        """Build a requests session with retry and timeout."""
        session = requests.Session()
        session.headers.update({"User-Agent": self.config.user_agent})
        retry = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_base_delay,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _rate_limit(self, domain: str) -> None:
        """Enforce per-domain crawl delay."""
        now = time.time()
        last = self._domain_timestamps[domain]
        wait = self.config.crawl_delay - (now - last)
        if wait > 0:
            time.sleep(wait)
        self._domain_timestamps[domain] = time.time()

    def fetch_page(self, url: str, domain: str = "", track_dedup: bool = True) -> CrawledPage:
        """Fetch a single page and return a CrawledPage with raw HTML."""
        if not domain:
            domain = urlparse(url).hostname or ""

        # Dedup
        normalized = _normalize_url(url)
        if track_dedup and normalized in self._seen_urls:
            return CrawledPage(
                competitor="", domain=domain, url=url,
                error="duplicate_url",
            )
        if track_dedup:
            self._seen_urls.add(normalized)

        # Robots.txt
        if self._robots and not self._robots.is_allowed(url):
            return CrawledPage(
                competitor="", domain=domain, url=url,
                error="blocked_by_robots_txt",
            )

        # Rate limit
        self._rate_limit(domain)

        # Fetch
        try:
            resp = self._session.get(
                url,
                timeout=self.config.request_timeout,
                allow_redirects=True,
                stream=True,
            )
            # Check response size
            content_length = int(resp.headers.get("content-length", 0))
            if content_length > self.config.max_response_bytes:
                resp.close()
                return CrawledPage(
                    competitor="", domain=domain, url=url,
                    http_status=resp.status_code,
                    error=f"response_too_large:{content_length}",
                )

            # Read with size limit
            content = b""
            for chunk in resp.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > self.config.max_response_bytes:
                    break
            resp.close()

            # Content-type check
            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return CrawledPage(
                    competitor="", domain=domain, url=url,
                    http_status=resp.status_code,
                    error=f"unsupported_content_type:{content_type}",
                )

            html = content.decode("utf-8", errors="replace")

            return CrawledPage(
                competitor="",
                domain=domain,
                url=url,
                canonical_url=resp.url,  # final URL after redirects
                main_content=html,  # raw HTML, to be extracted later
                http_status=resp.status_code,
                crawled_at=datetime.now(timezone.utc).isoformat(),
            )

        except requests.Timeout:
            return CrawledPage(
                competitor="", domain=domain, url=url,
                error="timeout",
            )
        except requests.ConnectionError:
            return CrawledPage(
                competitor="", domain=domain, url=url,
                error="connection_error",
            )
        except Exception as e:
            return CrawledPage(
                competitor="", domain=domain, url=url,
                error=f"fetch_error:{type(e).__name__}",
            )

    def discover_urls(self, start_url: str, domain: str, max_pages: int = 10) -> list[str]:
        """Discover internal links from a starting URL via BFS.

        Fetches the start_url to extract links, then discovers additional URLs.
        Returns list of discovered URLs (may include start_url).
        """
        # Normalize domain to handle www prefix
        normalized_domain = domain.removeprefix("www.")

        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_url, 0)]
        discovered: list[str] = []

        from bs4 import BeautifulSoup

        while queue and len(discovered) < max_pages:
            url, depth = queue.pop(0)
            normalized = _normalize_url(url)

            if normalized in visited:
                continue
            visited.add(normalized)

            parsed = urlparse(url)
            host = (parsed.hostname or "").removeprefix("www.")
            if host != normalized_domain:
                continue

            if not _is_relevant_url(url, self.config):
                continue

            discovered.append(url)

            if depth >= self.config.max_depth:
                continue

            # Fetch page to discover links (don't track dedup here)
            page = self.fetch_page(url, domain, track_dedup=False)
            if page.error or not page.main_content:
                continue

            try:
                soup = BeautifulSoup(page.main_content, "html.parser")
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    full_url = urljoin(url, href)
                    full_url, _ = urldefrag(full_url)
                    link_parsed = urlparse(full_url)
                    link_host = (link_parsed.hostname or "").removeprefix("www.")
                    if link_host == normalized_domain:
                        queue.append((full_url, depth + 1))
            except Exception:
                continue

        return discovered

    def reset(self) -> None:
        """Reset seen URLs (for new crawl session)."""
        self._seen_urls.clear()
        self._domain_timestamps.clear()
