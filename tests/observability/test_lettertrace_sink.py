"""Tests for LetterTrace sink integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from seo_aeo_geo_pipeline.observability.lettertrace_sink import (
    LetterTraceSink,
    create_lettertrace_sink,
    get_lettertrace_status,
    register_lettertrace_sink,
)


class TestLetterTraceStatus:
    def test_status_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("LETTERTRACE_API_KEY", raising=False)
        status = get_lettertrace_status()
        assert status["configured"] is False

    def test_status_when_configured(self, monkeypatch):
        monkeypatch.setenv("LETTERTRACE_API_KEY", "lt-test-key")
        monkeypatch.setenv("LETTERTRACE_BASE_URL", "https://custom.lettertrace.ai")
        monkeypatch.setenv("LETTERTRACE_PROJECT_ID", "proj-123")
        status = get_lettertrace_status()
        assert status["configured"] is True
        assert status["base_url"] == "https://custom.lettertrace.ai"
        assert status["project_id"] == "proj-123"


class TestLetterTraceSink:
    def test_not_configured_by_default(self):
        sink = LetterTraceSink(api_key="", base_url="https://api.lettertrace.ai")
        assert not sink.is_configured
        assert not sink.is_available

    def test_configured_with_key(self):
        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        assert sink.is_configured
        assert sink.is_available

    def test_call_noop_when_not_initialized(self):
        sink = LetterTraceSink(api_key="", base_url="https://api.lettertrace.ai")
        # Should not raise
        sink({"trace_id": "test", "operation": "test"})

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_initialization_success(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_session.get.return_value = mock_resp

        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        result = sink._ensure_client()

        assert result is True
        assert sink._session is mock_session
        mock_session.get.assert_called_once_with("https://api.lettertrace.ai/health", timeout=30)

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_initialization_connection_failure(self, mock_session_class):
        import requests
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.get.side_effect = requests.exceptions.ConnectionError("connection failed")

        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        result = sink._ensure_client()

        assert result is False
        assert sink._session is None

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_send_trace(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_session.post.return_value = mock_resp
        mock_session.get.return_value = MagicMock(status_code=200)

        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        trace_data = {
            "trace_id": "trace-123",
            "run_id": "run-456",
            "job_id": "job-789",
            "stage": "research",
            "operation": "plan_research",
            "model": "openrouter/test-model",
            "provider": "openrouter",
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-01T00:00:01Z",
            "latency_ms": 1000.0,
            "success": True,
            "error_type": None,
            "error_message": None,
            "retry_count": 0,
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
            "cost": 0.001,
            "metadata": {"custom": "data"},
        }

        sink(trace_data)

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args.args[0] == "https://api.lettertrace.ai/v1/traces"
        assert call_args.kwargs["json"]["trace_id"] == "trace-123"
        assert call_args.kwargs["json"]["run_id"] == "run-456"
        assert call_args.kwargs["json"]["job_id"] == "job-789"
        assert call_args.kwargs["json"]["stage"] == "research"
        assert call_args.kwargs["json"]["operation"] == "plan_research"

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_send_trace_with_error(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_session.post.return_value = mock_resp
        mock_session.get.return_value = MagicMock(status_code=200)

        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        trace_data = {
            "trace_id": "trace-123",
            "run_id": "run-456",
            "job_id": "job-789",
            "stage": "generation",
            "operation": "generate_article",
            "model": "openrouter/test-model",
            "provider": "openrouter",
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-01T00:00:05Z",
            "latency_ms": 5000.0,
            "success": False,
            "error_type": "RateLimitError",
            "error_message": "Rate limited",
            "retry_count": 2,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cost": None,
            "metadata": {},
        }

        sink(trace_data)

        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args.kwargs["json"]["success"] is False
        assert call_args.kwargs["json"]["error_type"] == "RateLimitError"
        assert call_args.kwargs["json"]["error_message"] == "Rate limited"

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_send_trace_http_error_swallowed(self, mock_session_class):
        """Test that HTTP errors are logged but not raised (graceful degradation)."""
        import requests
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        http_error = requests.exceptions.HTTPError("401", response=mock_resp)
        mock_session.post.side_effect = http_error
        mock_session.get.return_value = MagicMock(status_code=200)

        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        trace_data = {
            "trace_id": "trace-123",
            "run_id": "run-456",
            "job_id": "job-789",
            "stage": "research",
            "operation": "plan_research",
            "model": "openrouter/test-model",
            "provider": "openrouter",
            "started_at": "2026-01-01T00:00:00Z",
            "ended_at": "2026-01-01T00:00:01Z",
            "latency_ms": 1000.0,
            "success": True,
            "error_type": None,
            "error_message": None,
            "retry_count": 0,
            "input_tokens": 100,
            "output_tokens": 200,
            "total_tokens": 300,
            "cost": 0.001,
            "metadata": {},
        }

        # Should not raise - errors are swallowed per design
        sink(trace_data)

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_flush(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.get.return_value = MagicMock(status_code=200)

        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        sink.flush()
        # flush is no-op for HTTP-based sink, just verify no errors

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_shutdown(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.get.return_value = MagicMock(status_code=200)

        sink = LetterTraceSink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        # Initialize client by calling the sink
        sink({"trace_id": "test", "operation": "test", "success": True})
        sink.shutdown()
        mock_session.close.assert_called_once()
        assert sink._session is None


class TestCreateLetterTraceSink:
    def test_returns_none_when_not_configured(self):
        sink = create_lettertrace_sink(api_key="", base_url="https://api.lettertrace.ai")
        assert sink is None

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.requests.Session")
    def test_returns_sink_when_configured(self, mock_session_class):
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        mock_session.get.return_value = MagicMock(status_code=200)

        sink = create_lettertrace_sink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
        assert sink is not None
        assert isinstance(sink, LetterTraceSink)


class TestRegisterLetterTraceSink:
    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.create_lettertrace_sink", return_value=None)
    def test_returns_false_when_sink_not_created(self, mock_create):
        result = register_lettertrace_sink()
        assert result is False

    @patch("seo_aeo_geo_pipeline.observability.lettertrace_sink.create_lettertrace_sink")
    def test_returns_true_when_sink_registered(self, mock_create):
        mock_sink = MagicMock()
        mock_create.return_value = mock_sink

        with patch("seo_aeo_geo_pipeline.observability.llm_trace.register_trace_sink") as mock_register:
            result = register_lettertrace_sink(api_key="lt-test-key", base_url="https://api.lettertrace.ai")
            assert result is True
            mock_register.assert_called_once_with(mock_sink)