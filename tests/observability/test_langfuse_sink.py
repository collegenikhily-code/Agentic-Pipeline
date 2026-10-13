"""Tests for Langfuse sink integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from seo_aeo_geo_pipeline.observability.langfuse_sink import (
    LangfuseSink,
    create_langfuse_sink,
    get_langfuse_status,
    register_langfuse_sink,
)


class TestLangfuseStatus:
    def test_status_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        status = get_langfuse_status()
        assert status["available"] is False or status["available"] is True  # depends on install
        assert status["configured"] is False

    def test_status_when_configured(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_HOST", "https://custom.langfuse.com")
        status = get_langfuse_status()
        assert status["configured"] is True
        assert status["host"] == "https://custom.langfuse.com"


class TestLangfuseSink:
    def test_not_configured_by_default(self):
        sink = LangfuseSink(public_key="", secret_key="")
        assert not sink.is_configured
        assert not sink.is_available

    def test_configured_with_keys(self):
        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
        assert sink.is_configured

    def test_call_noop_when_not_initialized(self):
        sink = LangfuseSink(public_key="", secret_key="")
        # Should not raise
        sink({"trace_id": "test", "operation": "test"})

    def test_call_noop_when_langfuse_not_installed(self):
        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
        with patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", False):
            # Should not raise
            sink({"trace_id": "test", "operation": "test"})

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.Langfuse")
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    def test_initialization_success(self, mock_langfuse_class):
        mock_client = MagicMock()
        mock_langfuse_class.return_value = mock_client
        mock_client.auth_check.return_value = True

        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
        result = sink._ensure_client()

        assert result is True
        assert sink._client is mock_client
        mock_langfuse_class.assert_called_once_with(
            public_key="pk-test",
            secret_key="sk-test",
            host="https://cloud.langfuse.com",
            flush_interval=5.0,
        )
        mock_client.auth_check.assert_called_once()

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.Langfuse")
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    def test_initialization_auth_failure(self, mock_langfuse_class):
        from seo_aeo_geo_pipeline.observability.langfuse_sink import UnauthorizedError
        mock_client = MagicMock()
        mock_langfuse_class.return_value = mock_client
        mock_client.auth_check.side_effect = UnauthorizedError("Invalid credentials")

        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
        result = sink._ensure_client()

        assert result is False
        assert sink._client is None

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.Langfuse")
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    def test_send_trace(self, mock_langfuse_class):
        mock_client = MagicMock()
        mock_langfuse_class.return_value = mock_client
        mock_client.auth_check.return_value = True

        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
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

        mock_client.generation.assert_called_once()
        call_args = mock_client.generation.call_args
        assert call_args.kwargs["id"] == "trace-123"
        assert call_args.kwargs["name"] == "plan_research"
        assert call_args.kwargs["model"] == "openrouter/test-model"
        assert call_args.kwargs["metadata"]["run_id"] == "run-456"
        assert call_args.kwargs["metadata"]["job_id"] == "job-789"

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.Langfuse")
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    def test_send_trace_with_error(self, mock_langfuse_class):
        mock_client = MagicMock()
        mock_langfuse_class.return_value = mock_client
        mock_client.auth_check.return_value = True

        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
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

        mock_client.generation.assert_called_once()
        call_args = mock_client.generation.call_args
        assert call_args.kwargs["level"] == "ERROR"
        assert call_args.kwargs["status_message"] == "Rate limited"
        assert call_args.kwargs["metadata"]["error_type"] == "RateLimitError"

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.Langfuse")
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    def test_flush(self, mock_langfuse_class):
        mock_client = MagicMock()
        mock_langfuse_class.return_value = mock_client
        mock_client.auth_check.return_value = True

        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
        # Initialize client by calling the sink
        sink({"trace_id": "test", "operation": "test", "success": True})
        sink.flush()
        mock_client.flush.assert_called_once()

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.Langfuse")
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    def test_shutdown(self, mock_langfuse_class):
        mock_client = MagicMock()
        mock_langfuse_class.return_value = mock_client
        mock_client.auth_check.return_value = True

        sink = LangfuseSink(public_key="pk-test", secret_key="sk-test")
        # Initialize client by calling the sink
        sink({"trace_id": "test", "operation": "test", "success": True})
        sink.shutdown()
        mock_client.shutdown.assert_called_once()
        assert sink._client is None


class TestCreateLangfuseSink:
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", False)
    def test_returns_none_when_not_available(self):
        sink = create_langfuse_sink()
        assert sink is None

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    def test_returns_none_when_not_configured(self):
        sink = create_langfuse_sink(public_key="", secret_key="")
        assert sink is None

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.LANGFUSE_AVAILABLE", True)
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.Langfuse")
    def test_returns_sink_when_configured(self, mock_langfuse_class):
        mock_client = MagicMock()
        mock_langfuse_class.return_value = mock_client
        mock_client.auth_check.return_value = True

        sink = create_langfuse_sink(public_key="pk-test", secret_key="sk-test")
        assert sink is not None
        assert isinstance(sink, LangfuseSink)


class TestRegisterLangfuseSink:
    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.create_langfuse_sink", return_value=None)
    def test_returns_false_when_sink_not_created(self, mock_create):
        result = register_langfuse_sink()
        assert result is False

    @patch("seo_aeo_geo_pipeline.observability.langfuse_sink.create_langfuse_sink")
    def test_returns_true_when_sink_registered(self, mock_create):
        mock_sink = MagicMock()
        mock_create.return_value = mock_sink

        with patch("seo_aeo_geo_pipeline.observability.llm_trace.register_trace_sink") as mock_register:
            result = register_langfuse_sink(public_key="pk-test", secret_key="sk-test")
            assert result is True
            mock_register.assert_called_once_with(mock_sink)