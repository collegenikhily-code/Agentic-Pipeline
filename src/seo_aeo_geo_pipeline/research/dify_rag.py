"""Thin Dify RAG adapter - persistent knowledge/retrieval layer.

Dify provides evidence retrieval over a reusable research corpus.
This adapter wraps Dify's Knowledge API for retrieval-only operations.

Requires:
    DIFY_API_KEY - API key for Dify knowledge retrieval
    DIFY_BASE_URL - Dify instance URL (default: https://api.dify.ai)
    DIFY_DATASET_ID - Knowledge base dataset ID

Falls back to empty results when credentials are missing.
Does NOT use Dify as orchestrator or page generator.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.dify.ai"


@dataclass
class RetrievalResult:
    """Single retrieval result from Dify knowledge base."""
    content: str
    source_url: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class KnowledgeRetrieval:
    """Aggregated retrieval results for a query."""
    query: str
    results: list[RetrievalResult] = field(default_factory=list)
    total_results: int = 0
    provider: str = "dify"
    error: Optional[str] = None


class DifyRAGClient:
    """Thin client for Dify Knowledge Retrieval API.

    Usage:
        client = DifyRAGClient()
        knowledge = client.retrieve("meta ads mcp integration", top_k=5)
        for result in knowledge.results:
            print(result.content[:200])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        dataset_id: Optional[str] = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("DIFY_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DIFY_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self.dataset_id = dataset_id or os.environ.get("DIFY_DATASET_ID", "")
        self.timeout = timeout
        self._session = requests.Session()
        if self.api_key:
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })

    @property
    def is_configured(self) -> bool:
        """Check if Dify credentials are available."""
        return bool(self.api_key) and bool(self.dataset_id)

    def verify_dataset(self) -> bool:
        """Verify that the configured dataset ID is accessible.

        Uses GET /v1/datasets/{dataset_id} endpoint.
        """
        if not self.is_configured:
            return False

        verify_endpoint = f"{self.base_url}/v1/datasets/{self.dataset_id}"
        try:
            resp = self._session.get(
                verify_endpoint,
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            return resp.status_code == 200
        except Exception:
            return False

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        knowledge_base_ids: Optional[list[str]] = None,
    ) -> KnowledgeRetrieval:
        """Retrieve relevant knowledge from Dify knowledge base.

        Args:
            query: Search query (typically the keyword or research question)
            top_k: Maximum number of results to return
            knowledge_base_ids: Optional list of specific knowledge base IDs to search

        Returns:
            KnowledgeRetrieval with results or error
        """
        if not self.is_configured:
            logger.debug("Dify not configured - returning empty retrieval")
            error_msg = "DIFY_API_KEY not configured" if not self.api_key else "DIFY_DATASET_ID not configured"
            return KnowledgeRetrieval(
                query=query,
                results=[],
                total_results=0,
                error=error_msg,
            )

        # Use provided knowledge_base_ids or fall back to configured dataset_id
        kb_ids = knowledge_base_ids or [self.dataset_id]

        try:
            # Use the correct Dify API endpoint: POST /v1/datasets/{dataset_id}/retrieve
            dataset_id = kb_ids[0]
            endpoint = f"{self.base_url}/v1/datasets/{dataset_id}/retrieve"
            payload: dict[str, Any] = {
                "query": query,
                "top_k": top_k,
                "knowledge_base_ids": kb_ids,
            }

            resp = self._session.post(
                endpoint,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            # Dify API returns "records" with "segment" sub-objects
            for record in data.get("records", []):
                segment = record.get("segment", {})
                doc = segment.get("document", {})
                results.append(RetrievalResult(
                    content=segment.get("content", ""),
                    source_url=doc.get("name", ""),
                    score=record.get("score", 0.0),
                    metadata={"document_id": segment.get("document_id", ""), "position": segment.get("position", 0)},
                ))

            return KnowledgeRetrieval(
                query=query,
                results=results,
                total_results=len(results),
                provider="dify",
            )

        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Dify connection failed: {e}")
            return KnowledgeRetrieval(query=query, error=f"Connection failed: {e}")
        except requests.exceptions.Timeout as e:
            logger.warning(f"Dify request timed out: {e}")
            return KnowledgeRetrieval(query=query, error=f"Timeout: {e}")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            logger.warning(f"Dify HTTP error {status}: {e}")
            return KnowledgeRetrieval(query=query, error=f"HTTP {status}: {e}")
        except Exception as e:
            logger.warning(f"Dify retrieval failed: {e}")
            return KnowledgeRetrieval(query=query, error=f"Retrieval failed: {e}")

    def health_check(self) -> dict:
        """Check Dify API connectivity."""
        if not self.is_configured:
            return {"status": "not_configured", "message": "DIFY_API_KEY not set"}
        try:
            resp = self._session.get(f"{self.base_url}/knowledge", timeout=10)
            resp.raise_for_status()
            return {"status": "ok", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}
