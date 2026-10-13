"""SE Ranking REST API adapter.

Thin HTTP client responsible only for:
- Authentication via API key header
- Request construction
- Timeout handling
- Safe error handling
- Pagination where required
- Returning raw structured responses

All clustering and opportunity logic lives elsewhere.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests


_BASE_URL = "https://api.seranking.com/v1"


class SERankingError(Exception):
    """Base error for SE Ranking API operations."""

    def __init__(self, message: str, status_code: int = 0, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class SERankingAuthError(SERankingError):
    """Authentication failed."""


class SERankingRateLimitError(SERankingError):
    """Rate limit exceeded."""


class SERankingClient:
    """Thin REST client for SE Ranking Data API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 2,
    ):
        self.api_key = api_key or os.environ.get("SE_RANKING_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Token {self.api_key}",
                "Accept": "application/json",
            }
        )

    def test_auth(self) -> dict:
        """Make a minimal request to validate credentials.

        Returns the subscription details on success.
        Raises SERankingAuthError on 401/403.
        """
        try:
            resp = self._session.get(
                f"{_BASE_URL}/account/subscription",
                timeout=self.timeout,
            )
            if resp.status_code in (401, 403):
                raise SERankingAuthError(
                    f"Authentication failed (HTTP {resp.status_code}). "
                    "Check SE_RANKING_API_KEY.",
                    status_code=resp.status_code,
                )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError, ConnectionError) as e:
            raise SERankingError(f"Connection failed: {e}") from e
        except requests.exceptions.Timeout as e:
            raise SERankingError(f"Request timed out: {e}") from e

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> Any:
        """Execute an HTTP request with retry on transient errors."""
        url = f"{_BASE_URL}{path}"
        last_err: Optional[Exception] = None

        for attempt in range(1 + self.max_retries):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    if attempt < self.max_retries:
                        time.sleep(retry_after)
                        continue
                    raise SERankingRateLimitError(
                        "Rate limit exceeded",
                        status_code=429,
                    )
                if resp.status_code in (401, 403):
                    raise SERankingAuthError(
                        f"Authentication failed (HTTP {resp.status_code})",
                        status_code=resp.status_code,
                    )
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.ConnectionError as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue
            except requests.exceptions.Timeout as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
                    continue

        raise SERankingError(f"Request failed after retries: {last_err}")

    def get_domain_competitors(
        self,
        domain: str,
        source: str = "us",
        with_subdomains: bool = True,
        limit: int = 20,
    ) -> list[dict]:
        """Get organic competitors for a domain.

        GET /v1/domain/competitors
        """
        params: dict[str, Any] = {
            "source": source,
            "domain": domain,
            "with_subdomains": 1 if with_subdomains else 0,
            "limit": limit,
        }
        return self._request("GET", "/domain/competitors", params=params)

    def get_domain_keywords(
        self,
        domain: Optional[str] = None,
        url: Optional[str] = None,
        source: str = "us",
        keyword_type: str = "organic",
        with_subdomains: bool = True,
        limit: int = 100,
        page: int = 1,
        order_field: str = "traffic",
        order_type: str = "desc",
        intents: Optional[list[str]] = None,
    ) -> list[dict]:
        """Get keywords a domain or URL ranks for (single page).

        GET /v1/domain/keywords
        Returns a list of keyword dicts.
        """
        params: dict[str, Any] = {
            "source": source,
            "type": keyword_type,
            "with_subdomains": 1 if with_subdomains else 0,
            "limit": min(limit, 1000),
            "page": page,
            "order_field": order_field,
            "order_type": order_type,
        }
        if domain:
            params["domain"] = domain
        if url:
            params["url"] = url
        if intents:
            params["intents"] = ",".join(intents)
        return self._request("GET", "/domain/keywords", params=params)

    def get_domain_keywords_all(
        self,
        domain: Optional[str] = None,
        url: Optional[str] = None,
        source: str = "us",
        keyword_type: str = "organic",
        with_subdomains: bool = True,
        target_count: int = 300,
        page_size: int = 10,
        order_field: str = "traffic",
        order_type: str = "desc",
        intents: Optional[list[str]] = None,
        max_pages: int = 50,
    ) -> list[dict]:
        """Paginate through /v1/domain/keywords until target_count is reached.

        The SE Ranking API returns up to ~10 results per page regardless of
        the limit parameter. This method pages through results automatically.

        Stops when:
        - target_count keywords collected, or
        - fewer results than page_size returned (last page), or
        - max_pages reached (safety bound)

        Returns the combined list of keyword dicts.
        """
        all_keywords: list[dict] = []
        page = 1

        while len(all_keywords) < target_count and page <= max_pages:
            params: dict[str, Any] = {
                "source": source,
                "type": keyword_type,
                "with_subdomains": 1 if with_subdomains else 0,
                "limit": page_size,
                "page": page,
                "order_field": order_field,
                "order_type": order_type,
            }
            if domain:
                params["domain"] = domain
            if url:
                params["url"] = url
            if intents:
                params["intents"] = ",".join(intents)

            raw = self._request("GET", "/domain/keywords", params=params)

            # API returns a list directly
            if isinstance(raw, list):
                page_records = raw
            elif isinstance(raw, dict):
                page_records = raw.get("keywords") or raw.get("result") or []
            else:
                page_records = []

            if not page_records:
                break

            all_keywords.extend(page_records)

            # If fewer records than page_size, this is the last page
            if len(page_records) < page_size:
                break

            page += 1

        return all_keywords

    def get_keyword_overlap(
        self,
        domain1: str,
        domain2: str,
        source: str = "us",
        keyword_type: str = "organic",
    ) -> dict:
        """Get keyword overlap/gap between two domains.

        GET /v1/domain/keywords/overlap
        Returns overlap data with only_domain1, only_domain2, common.
        """
        params: dict[str, Any] = {
            "source": source,
            "domain1": domain1,
            "domain2": domain2,
            "type": keyword_type,
        }
        return self._request("GET", "/domain/keywords/overlap", params=params)

    def get_related_keywords(
        self,
        keyword: str,
        source: str = "us",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get keywords related by overlapping SERP results.

        GET /v1/keywords/related
        Returns {"total": N, "keywords": [...]}
        """
        params: dict[str, Any] = {
            "source": source,
            "keyword": keyword,
            "limit": limit,
            "offset": offset,
        }
        return self._request("GET", "/keywords/related", params=params)

    def get_question_keywords(
        self,
        keyword: str,
        source: str = "us",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get question-form keywords for a seed keyword.

        GET /v1/keywords/questions
        Returns {"total": N, "keywords": [...]}
        """
        params: dict[str, Any] = {
            "source": source,
            "keyword": keyword,
            "limit": limit,
            "offset": offset,
        }
        return self._request("GET", "/keywords/questions", params=params)

    def get_keyword_metrics(
        self,
        keywords: list[str],
        source: str = "us",
    ) -> list[dict]:
        """Get metrics for a list of keywords (bulk).

        POST /v1/keywords/export
        Returns [{"keyword": ..., "volume": ..., "difficulty": ..., ...}]
        """
        json_body: dict[str, Any] = {
            "keywords": keywords,
        }
        return self._request(
            "POST",
            f"/keywords/export?source={source}",
            json_body=json_body,
        )
