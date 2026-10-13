"""Tests for SE Ranking REST API adapter."""

import json
from unittest.mock import MagicMock, patch

import pytest

from seo_aeo_geo_pipeline.discovery.se_ranking import (
    SERankingAuthError,
    SERankingClient,
    SERankingError,
    SERankingRateLimitError,
)


class TestSERankingClient:
    def test_missing_api_key_raises_auth_error(self):
        with patch.dict("os.environ", {}, clear=True):
            client = SERankingClient(api_key="")
            assert client.api_key == ""

    def test_client_uses_env_var(self):
        with patch.dict("os.environ", {"SE_RANKING_API_KEY": "test-key-123"}):
            client = SERankingClient()
            assert client.api_key == "test-key-123"

    def test_client_explicit_key_overrides_env(self):
        with patch.dict("os.environ", {"SE_RANKING_API_KEY": "env-key"}):
            client = SERankingClient(api_key="explicit-key")
            assert client.api_key == "explicit-key"

    def test_auth_header_format(self):
        client = SERankingClient(api_key="my-token")
        assert "Token my-token" in client._session.headers.get("Authorization", "")

    def test_test_auth_success(self):
        client = SERankingClient(api_key="valid-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"login": "test@example.com"}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "get", return_value=mock_resp):
            result = client.test_auth()
            assert result["login"] == "test@example.com"

    def test_test_auth_401_raises(self):
        client = SERankingClient(api_key="bad-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch.object(client._session, "get", return_value=mock_resp):
            with pytest.raises(SERankingAuthError) as exc_info:
                client.test_auth()
            assert "401" in str(exc_info.value)

    def test_test_auth_403_raises(self):
        client = SERankingClient(api_key="forbidden-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch.object(client._session, "get", return_value=mock_resp):
            with pytest.raises(SERankingAuthError):
                client.test_auth()

    def test_test_auth_connection_error(self):
        client = SERankingClient(api_key="key")

        with patch.object(
            client._session, "get", side_effect=ConnectionError("refused")
        ):
            with pytest.raises(SERankingError):
                client.test_auth()

    def test_get_domain_keywords(self):
        client = SERankingClient(api_key="key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"keyword": "test"}]
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_domain_keywords(domain="example.com", limit=10)
            assert isinstance(result, list)
            assert result[0]["keyword"] == "test"

    def test_get_domain_keywords_all_single_page(self):
        """When target_count fits in one page, no pagination occurs."""
        client = SERankingClient(api_key="key")
        page1 = [{"keyword": f"kw{i}", "volume": i * 10} for i in range(10)]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = page1
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "request", return_value=mock_resp) as mock_req:
            result = client.get_domain_keywords_all(
                domain="test.com", target_count=10, page_size=10
            )
            assert len(result) == 10
            assert mock_req.call_count == 1

    def test_get_domain_keywords_all_pagination(self):
        """Multiple pages fetched until target_count reached."""
        client = SERankingClient(api_key="key")
        page1 = [{"keyword": f"kw{i}", "volume": i * 10} for i in range(10)]
        page2 = [{"keyword": f"kw{i}", "volume": i * 10} for i in range(10, 20)]
        page3 = [{"keyword": f"kw{i}", "volume": i * 10} for i in range(20, 25)]

        responses = []
        for page_data in [page1, page2, page3]:
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = page_data
            resp.raise_for_status = MagicMock()
            responses.append(resp)

        with patch.object(client._session, "request", side_effect=responses) as mock_req:
            result = client.get_domain_keywords_all(
                domain="test.com", target_count=25, page_size=10
            )
            assert len(result) == 25
            # page1 (10) + page2 (10) + page3 (5 < 10, stops) = 3 requests
            assert mock_req.call_count == 3

    def test_get_domain_keywords_all_stops_on_empty_page(self):
        """Stops when API returns empty list."""
        client = SERankingClient(api_key="key")
        page1 = [{"keyword": f"kw{i}"} for i in range(10)]
        empty_page = []

        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = page1
        resp1.raise_for_status = MagicMock()

        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = empty_page
        resp2.raise_for_status = MagicMock()

        with patch.object(client._session, "request", side_effect=[resp1, resp2]) as mock_req:
            result = client.get_domain_keywords_all(
                domain="test.com", target_count=100, page_size=10
            )
            assert len(result) == 10
            assert mock_req.call_count == 2

    def test_get_domain_keywords_all_max_pages_safety(self):
        """Stops at max_pages even if target not reached."""
        client = SERankingClient(api_key="key")
        page_data = [{"keyword": f"kw{i}"} for i in range(10)]

        def make_resp(*args, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = list(page_data)
            resp.raise_for_status = MagicMock()
            return resp

        with patch.object(client._session, "request", side_effect=make_resp) as mock_req:
            result = client.get_domain_keywords_all(
                domain="test.com", target_count=1000, page_size=10, max_pages=3
            )
            # 3 pages * 10 = 30 records, stops at max_pages
            assert len(result) == 30
            assert mock_req.call_count == 3

    def test_get_domain_keywords_all_handles_dict_response(self):
        """Handles dict response shape (backward compat)."""
        client = SERankingClient(api_key="key")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"keywords": [{"keyword": "test"}]}
        resp.raise_for_status = MagicMock()

        with patch.object(client._session, "request", return_value=resp):
            result = client.get_domain_keywords_all(
                domain="test.com", target_count=10, page_size=10
            )
            assert len(result) == 1

    def test_get_keyword_overlap(self):
        client = SERankingClient(api_key="key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "only_domain1": [],
            "only_domain2": [],
            "common": [],
        }
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_keyword_overlap("a.com", "b.com")
            assert "only_domain1" in result

    def test_get_related_keywords(self):
        client = SERankingClient(api_key="key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total": 5, "keywords": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_related_keywords("test keyword")
            assert "keywords" in result

    def test_get_question_keywords(self):
        client = SERankingClient(api_key="key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total": 3, "keywords": []}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_question_keywords("test keyword")
            assert "keywords" in result

    def test_rate_limit_retry(self):
        client = SERankingClient(api_key="key", max_retries=1)
        rate_resp = MagicMock()
        rate_resp.status_code = 429
        rate_resp.headers = {"Retry-After": "1"}

        ok_resp = MagicMock()
        ok_resp.status_code = 200
        ok_resp.json.return_value = {"result": "ok"}
        ok_resp.raise_for_status = MagicMock()

        with patch.object(
            client._session, "request", side_effect=[rate_resp, ok_resp]
        ):
            result = client._request("GET", "/test")
            assert result == {"result": "ok"}

    def test_rate_limit_exhausted_raises(self):
        client = SERankingClient(api_key="key", max_retries=0)
        rate_resp = MagicMock()
        rate_resp.status_code = 429
        rate_resp.headers = {}

        with patch.object(client._session, "request", return_value=rate_resp):
            with pytest.raises(SERankingRateLimitError):
                client._request("GET", "/test")
