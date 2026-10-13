"""Tests for DifyIngestionClient with mocked HTTP."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from seo_aeo_geo_pipeline.intelligence.ingest import (
    DifyIngestionClient,
    IngestionResult,
    IngestionSummary,
)
from seo_aeo_geo_pipeline.intelligence.models import IntelligenceRecord, SerankingMeta


def _make_record(url="https://example.com/page", domain="example.com"):
    return IntelligenceRecord(
        url=url,
        competitor_domain=domain,
        title="Test Page",
        content="Test content",
        page_type="product",
        seranking=SerankingMeta(
            keyword="test kw",
            cluster_id="kc-1",
            intent="commercial",
            search_volume=1000,
            difficulty=30.0,
            ranking_position=5,
        ),
    )


class TestDifyIngestionClient:
    def test_not_configured_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            client = DifyIngestionClient(api_key="")
            assert not client.is_configured

    def test_configured_with_key(self):
        client = DifyIngestionClient(api_key="test-key")
        assert client.is_configured

    def test_configured_from_env(self):
        with patch.dict("os.environ", {"DIFY_API_KEY": "env-key"}):
            client = DifyIngestionClient()
            assert client.is_configured
            assert client.api_key == "env-key"

    def test_create_dataset_not_configured(self):
        client = DifyIngestionClient(api_key="")
        result = client.create_dataset("Test")
        assert not result.success
        assert "DIFY_API_KEY" in result.error

    def test_create_dataset_success(self):
        client = DifyIngestionClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "dataset-123", "name": "Test Dataset"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client.create_dataset("Test Dataset", "A test dataset")
            assert result.success
            assert result.dataset_id == "dataset-123"
            call_args = mock_post.call_args
            assert "/v1/datasets" in call_args[0][0]
            assert call_args[1]["json"]["name"] == "Test Dataset"

    def test_create_dataset_http_error(self):
        client = DifyIngestionClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        http_err = requests.exceptions.HTTPError(response=mock_resp)

        with patch.object(client._session, "post", side_effect=http_err):
            result = client.create_dataset("Test")
            assert not result.success
            assert "403" in result.error

    def test_verify_dataset_success(self):
        client = DifyIngestionClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.verify_dataset("dataset-123") is True

    def test_verify_dataset_not_accessible(self):
        client = DifyIngestionClient(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.verify_dataset("bad-id") is False

    def test_ensure_dataset_uses_existing(self):
        client = DifyIngestionClient(api_key="test-key")
        with patch.object(client, "verify_dataset", return_value=True):
            result = client.ensure_dataset("Test", existing_dataset_id="existing-123")
            assert result.success
            assert result.dataset_id == "existing-123"

    def test_ensure_dataset_creates_new(self):
        client = DifyIngestionClient(api_key="test-key")
        with patch.object(client, "verify_dataset", return_value=False):
            with patch.object(client, "create_dataset") as mock_create:
                mock_create.return_value = IngestionResult(
                    success=True, dataset_id="new-456"
                )
                result = client.ensure_dataset("Test", existing_dataset_id="bad-id")
                assert result.success
                assert result.dataset_id == "new-456"
                mock_create.assert_called_once()

    def test_ingest_record_not_configured(self):
        client = DifyIngestionClient(api_key="")
        record = _make_record()
        result = client.ingest_record(record, "dataset-123")
        assert not result.success
        assert "DIFY_API_KEY" in result.error

    def test_ingest_record_success(self):
        client = DifyIngestionClient(api_key="test-key")
        record = _make_record()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"document": {"id": "doc-789"}}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client.ingest_record(record, "dataset-123")
            assert result.success
            assert result.document_id == "doc-789"
            call_args = mock_post.call_args
            assert "/v1/datasets/dataset-123/document/create_by_text" in call_args[0][0]
            payload = call_args[1]["json"]
            assert "test kw" in payload["text"]  # provenance preserved
            assert "kc-1" in payload["text"]
            assert "https://example.com/page" in payload["text"]

    def test_ingest_record_http_error(self):
        client = DifyIngestionClient(api_key="test-key")
        record = _make_record()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal error"
        http_err = requests.exceptions.HTTPError(response=mock_resp)

        with patch.object(client._session, "post", side_effect=http_err):
            result = client.ingest_record(record, "dataset-123")
            assert not result.success
            assert "500" in result.error

    def test_ingest_batch(self):
        client = DifyIngestionClient(api_key="test-key")
        records = [
            _make_record(url="https://a.com/1", domain="a.com"),
            _make_record(url="https://b.com/2", domain="b.com"),
            _make_record(url="https://c.com/3", domain="c.com"),
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"document": {"id": "doc-1"}}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            summary = client.ingest_batch(records, "dataset-123")
            assert summary.total == 3
            assert summary.succeeded == 3
            assert summary.failed == 0
            assert len(summary.document_ids) == 3

    def test_ingest_batch_partial_failure(self):
        client = DifyIngestionClient(api_key="test-key")
        records = [
            _make_record(url="https://a.com/1", domain="a.com"),
            _make_record(url="https://b.com/2", domain="b.com"),
        ]

        responses = [
            MagicMock(status_code=200, json=lambda: {"document": {"id": "doc-1"}}),
            MagicMock(status_code=500, text="error"),
        ]
        responses[0].raise_for_status = MagicMock()
        responses[1].raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=responses[1]
        )

        with patch.object(client._session, "post", side_effect=responses):
            summary = client.ingest_batch(records, "dataset-123")
            assert summary.total == 2
            assert summary.succeeded == 1
            assert summary.failed == 1
            assert len(summary.errors) == 1
