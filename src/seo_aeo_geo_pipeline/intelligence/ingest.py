"""Dify ingestion client for competitor intelligence records.

Extends the existing retrieval-only DifyRAGClient with write capabilities.
Creates documents in a Dify knowledge dataset with full provenance metadata.

Dify Knowledge API endpoints used:
    POST /v1/datasets                          - create a new dataset
    POST /v1/datasets/{id}/document/create_by_text  - create document by text
    GET  /v1/datasets/{id}                    - verify dataset exists
    POST /v1/datasets/{id}/retrieve           - retrieve knowledge (existing)

Does NOT use Dify as orchestrator or page generator.
Does NOT print API keys.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from .models import IntelligenceRecord

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.dify.ai"


@dataclass
class IngestionResult:
    """Result of an ingestion operation."""

    success: bool
    dataset_id: str = ""
    document_id: str = ""
    message: str = ""
    error: Optional[str] = None


@dataclass
class IngestionSummary:
    """Aggregated result of batch ingestion."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    dataset_id: str = ""
    document_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DifyIngestionClient:
    """Client for ingesting intelligence records into Dify knowledge datasets.

    Usage:
        client = DifyIngestionClient()
        dataset_id = client.ensure_dataset("Competitor Intelligence")
        result = client.ingest_record(record, dataset_id)
        summary = client.ingest_batch(records, dataset_id)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60,
    ):
        self.api_key = api_key or os.environ.get("DIFY_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DIFY_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        if self.api_key:
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
            })

    @property
    def is_configured(self) -> bool:
        """Check if Dify credentials are available."""
        return bool(self.api_key)

    def _headers(self, content_type: str = "application/json") -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": content_type,
        }

    def create_dataset(self, name: str, description: str = "") -> IngestionResult:
        """Create a new Dify knowledge dataset.

        Uses POST /v1/datasets endpoint.
        """
        if not self.is_configured:
            return IngestionResult(
                success=False,
                error="DIFY_API_KEY not configured",
            )

        endpoint = f"{self.base_url}/v1/datasets"
        payload: dict[str, Any] = {
            "name": name,
            "permission": "all_team_members",
        }
        if description:
            payload["description"] = description

        try:
            resp = self._session.post(
                endpoint,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            dataset_id = data.get("id", "")
            logger.info(f"Created Dify dataset: {name} (id={dataset_id})")
            return IngestionResult(
                success=True,
                dataset_id=dataset_id,
                message=f"Dataset created: {name}",
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            body = ""
            try:
                body = e.response.text[:500] if e.response is not None else ""
            except Exception:
                pass
            logger.warning(f"Dify create_dataset HTTP {status}: {body}")
            return IngestionResult(
                success=False,
                error=f"HTTP {status}: {body}",
            )
        except Exception as e:
            logger.warning(f"Dify create_dataset failed: {e}")
            return IngestionResult(success=False, error=str(e))

    def ensure_dataset(
        self,
        name: str,
        description: str = "",
        existing_dataset_id: Optional[str] = None,
    ) -> IngestionResult:
        """Ensure a dataset exists, returning its ID.

        If existing_dataset_id is provided and accessible, returns it.
        Otherwise creates a new dataset with the given name.
        """
        # Try existing dataset first
        if existing_dataset_id:
            if self.verify_dataset(existing_dataset_id):
                return IngestionResult(
                    success=True,
                    dataset_id=existing_dataset_id,
                    message="Using existing dataset",
                )
            logger.info(f"Existing dataset {existing_dataset_id} not accessible, creating new one")

        # Create new dataset
        return self.create_dataset(name, description)

    def verify_dataset(self, dataset_id: str) -> bool:
        """Verify that a dataset exists and is accessible.

        Uses GET /v1/datasets/{dataset_id} endpoint.
        """
        if not self.is_configured or not dataset_id:
            return False

        endpoint = f"{self.base_url}/v1/datasets/{dataset_id}"
        try:
            resp = self._session.get(
                endpoint,
                headers=self._headers(),
                timeout=self.timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def ingest_record(
        self,
        record: IntelligenceRecord,
        dataset_id: str,
        document_name: Optional[str] = None,
    ) -> IngestionResult:
        """Ingest a single IntelligenceRecord into a Dify dataset.

        Creates a document by text with full provenance metadata preserved
        in the document body.
        """
        if not self.is_configured:
            return IngestionResult(success=False, error="DIFY_API_KEY not configured")
        if not dataset_id:
            return IngestionResult(success=False, error="dataset_id required")
        if not record.url:
            return IngestionResult(success=False, error="record.url required")

        doc_name = document_name or f"{record.competitor_domain}-{record.content_hash or record.url}"
        # Clean document name for Dify (no special chars that break API)
        doc_name = doc_name.replace("/", "-").replace(":", "-")[:200]

        endpoint = f"{self.base_url}/v1/datasets/{dataset_id}/document/create_by_text"
        payload: dict[str, Any] = {
            "name": doc_name,
            "text": record.to_dify_text(),
            "indexing_technique": "high_quality",
            "process_rule": {
                "mode": "custom",
                "rules": {
                    "pre_processing_rules": [
                        {"id": "remove_extra_spaces", "enabled": True},
                        {"id": "remove_urls_emails", "enabled": False},
                    ],
                    "segmentation": {
                        "separator": "\n\n",
                        "max_tokens": 512,
                    },
                },
            },
        }

        try:
            resp = self._session.post(
                endpoint,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            document_id = data.get("document", {}).get("id", "") or data.get("id", "")
            logger.info(f"Ingested record for {record.url} into dataset {dataset_id} (doc={document_id})")
            return IngestionResult(
                success=True,
                dataset_id=dataset_id,
                document_id=document_id,
                message=f"Ingested: {record.url}",
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            body = ""
            try:
                body = e.response.text[:500] if e.response is not None else ""
            except Exception:
                pass
            logger.warning(f"Dify ingest_record HTTP {status} for {record.url}: {body}")
            return IngestionResult(
                success=False,
                error=f"HTTP {status}: {body}",
            )
        except Exception as e:
            logger.warning(f"Dify ingest_record failed for {record.url}: {e}")
            return IngestionResult(success=False, error=str(e))

    def ingest_batch(
        self,
        records: list[IntelligenceRecord],
        dataset_id: str,
    ) -> IngestionSummary:
        """Ingest a batch of IntelligenceRecords into a Dify dataset.

        Returns an IngestionSummary with per-record success/failure counts.
        """
        summary = IngestionSummary(
            total=len(records),
            dataset_id=dataset_id,
        )

        if not self.is_configured:
            summary.errors.append("DIFY_API_KEY not configured")
            return summary
        if not dataset_id:
            summary.errors.append("dataset_id required")
            return summary

        for record in records:
            result = self.ingest_record(record, dataset_id)
            if result.success:
                summary.succeeded += 1
                if result.document_id:
                    summary.document_ids.append(result.document_id)
            else:
                summary.failed += 1
                if result.error:
                    summary.errors.append(f"{record.url}: {result.error}")

        logger.info(
            f"Ingestion batch complete: {summary.succeeded}/{summary.total} succeeded, "
            f"{summary.failed} failed"
        )
        return summary
