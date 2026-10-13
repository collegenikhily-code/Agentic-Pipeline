"""Tests for Dify RAG adapter."""

import pytest
import requests
from unittest.mock import MagicMock, patch
from seo_aeo_geo_pipeline.research.dify_rag import DifyRAGClient, KnowledgeRetrieval


class TestDifyRAGClient:
    def test_not_configured_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            client = DifyRAGClient(api_key="")
            assert not client.is_configured

    def test_not_configured_without_dataset_id(self):
        with patch.dict("os.environ", {}, clear=True):
            client = DifyRAGClient(api_key="test-key", dataset_id="")
            assert not client.is_configured

    def test_configured_with_key_and_dataset_id(self):
        client = DifyRAGClient(api_key="test-key", dataset_id="test-dataset-id")
        assert client.is_configured

    def test_configured_from_env(self):
        with patch.dict("os.environ", {"DIFY_API_KEY": "env-key", "DIFY_DATASET_ID": "env-dataset-id"}):
            client = DifyRAGClient()
            assert client.is_configured
            assert client.api_key == "env-key"
            assert client.dataset_id == "env-dataset-id"

    def test_graceful_fallback_when_not_configured(self):
        client = DifyRAGClient(api_key="", dataset_id="")
        result = client.retrieve("test query")
        assert isinstance(result, KnowledgeRetrieval)
        assert result.results == []
        assert result.error is not None
        assert "DIFY_API_KEY" in result.error

    def test_graceful_fallback_when_no_dataset_id(self):
        client = DifyRAGClient(api_key="test-key", dataset_id="")
        result = client.retrieve("test query")
        assert isinstance(result, KnowledgeRetrieval)
        assert result.results == []
        assert result.error is not None
        assert "DIFY_DATASET_ID" in result.error

    def test_health_check_not_configured(self):
        client = DifyRAGClient(api_key="")
        health = client.health_check()
        assert health["status"] == "not_configured"

    def test_retrieve_returns_results(self):
        client = DifyRAGClient(api_key="test-key", dataset_id="test-dataset-id")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "records": [
                {
                    "segment": {"content": "test content", "document_id": "doc1", "position": 1, "document": {"name": "test.md"}},
                    "score": 0.9,
                },
                {
                    "segment": {"content": "more content", "document_id": "doc2", "position": 2, "document": {"name": "other.md"}},
                    "score": 0.7,
                },
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp):
            result = client.retrieve("test query", top_k=5)
            assert result.total_results == 2
            assert result.results[0].content == "test content"
            assert result.results[0].score == 0.9

    def test_retrieve_uses_dataset_id_in_endpoint(self):
        client = DifyRAGClient(api_key="test-key", dataset_id="my-dataset-123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.retrieve("test query")
            call_args = mock_post.call_args
            assert "/v1/datasets/my-dataset-123/retrieve" in call_args[0][0]

    def test_retrieve_handles_connection_error(self):
        client = DifyRAGClient(api_key="test-key", dataset_id="test-dataset-id")
        with patch.object(client._session, "post", side_effect=ConnectionError("refused")):
            result = client.retrieve("test")
            assert result.error is not None
            assert "refused" in result.error

    def test_retrieve_handles_timeout(self):
        client = DifyRAGClient(api_key="test-key", dataset_id="test-dataset-id")
        import requests
        with patch.object(client._session, "post", side_effect=requests.exceptions.Timeout()):
            result = client.retrieve("test")
            assert result.error is not None
            assert "Timeout" in result.error

    def test_retrieve_handles_http_error(self):
        client = DifyRAGClient(api_key="test-key", dataset_id="test-dataset-id")
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        http_err = requests.exceptions.HTTPError(response=mock_resp)
        with patch.object(client._session, "post", side_effect=http_err):
            result = client.retrieve("test")
            assert result.error is not None
            assert "403" in result.error
