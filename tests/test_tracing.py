"""Tests for LLM tracing integration."""

import pytest

from seo_aeo_geo_pipeline.observability.llm_trace import (
    LLMTraceRecord,
    get_trace_collector,
    record_llm_call,
    set_trace_context,
    clear_trace_context,
    trace_context,
    instrument_litellm_call,
)


class TestLLMTraceRecord:
    def test_to_dict(self):
        rec = LLMTraceRecord(
            trace_id="abc123",
            run_id="run1",
            job_id="job1",
            stage="research",
            operation="plan_research",
            model="openrouter/test-model",
            provider="openrouter",
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:01+00:00",
            latency_ms=1000.0,
            success=True,
            input_tokens=100,
            output_tokens=200,
            total_tokens=300,
            cost=0.001,
        )
        d = rec.to_dict()
        assert d["trace_id"] == "abc123"
        assert d["provider"] == "openrouter"
        assert d["total_tokens"] == 300


class TestTraceContext:
    def test_set_and_get(self):
        clear_trace_context()
        set_trace_context(run_id="r1", job_id="j1", stage="research")
        ctx = get_trace_collector()
        # get_trace_collector returns the collector, use the context functions
        from seo_aeo_geo_pipeline.observability.llm_trace import get_trace_context
        assert get_trace_context()["run_id"] == "r1"
        assert get_trace_context()["job_id"] == "j1"
        assert get_trace_context()["stage"] == "research"
        clear_trace_context()

    def test_context_manager(self):
        clear_trace_context()
        with trace_context(run_id="r2", job_id="j2", stage="generation"):
            from seo_aeo_geo_pipeline.observability.llm_trace import get_trace_context
            assert get_trace_context()["run_id"] == "r2"
        # After context exit, should be cleared
        from seo_aeo_geo_pipeline.observability.llm_trace import get_trace_context
        assert get_trace_context()["run_id"] == ""


class TestRecordLLMCall:
    def test_record_success(self):
        clear_trace_context()
        set_trace_context(run_id="test-run", job_id="test-job", stage="test")
        collector = get_trace_collector()
        collector.clear()

        rec = record_llm_call(
            operation="test_op",
            model="openrouter/test-model",
            stage="test",
            success=True,
            latency_ms=500.0,
        )
        assert rec["success"] is True
        assert rec["operation"] == "test_op"
        assert rec["provider"] == "openrouter"
        assert rec["latency_ms"] == 500.0

        records = collector.get_records(run_id="test-run")
        assert len(records) == 1
        clear_trace_context()

    def test_record_failure(self):
        clear_trace_context()
        set_trace_context(run_id="test-run-2", job_id="test-job", stage="test")
        collector = get_trace_collector()
        collector.clear()

        try:
            raise ValueError("test error")
        except ValueError as e:
            rec = record_llm_call(
                operation="test_op",
                model="openrouter/test-model",
                stage="test",
                success=False,
                error=e,
                latency_ms=100.0,
            )
        assert rec["success"] is False
        assert rec["error_type"] == "ValueError"
        assert "test error" in rec["error_message"]
        clear_trace_context()


class TestInstrumentLiteLLMCall:
    def test_instruments_success(self):
        clear_trace_context()
        set_trace_context(run_id="test-run-3", job_id="test-job", stage="test")
        collector = get_trace_collector()
        collector.clear()

        def mock_completion(**kwargs):
            class MockResponse:
                class MockUsage:
                    prompt_tokens = 50
                    completion_tokens = 100
                    total_tokens = 150
                usage = MockUsage()
                choices = [type("Choice", (), {"message": type("Msg", (), {"content": "response"})()})()]
            return MockResponse()

        response = instrument_litellm_call(
            mock_completion,
            operation="test_gen",
            stage="generation",
            model="openrouter/test-model",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=100,
        )
        assert response is not None

        records = collector.get_records(run_id="test-run-3")
        assert len(records) == 1
        assert records[0]["operation"] == "test_gen"
        assert records[0]["success"] is True
        assert records[0]["input_tokens"] == 50
        assert records[0]["output_tokens"] == 100
        clear_trace_context()

    def test_instruments_failure(self):
        clear_trace_context()
        set_trace_context(run_id="test-run-4", job_id="test-job", stage="test")
        collector = get_trace_collector()
        collector.clear()

        def mock_completion_fail(**kwargs):
            raise RuntimeError("API error")

        try:
            instrument_litellm_call(
                mock_completion_fail,
                operation="test_gen",
                stage="generation",
                model="openrouter/test-model",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=100,
            )
        except RuntimeError:
            pass

        records = collector.get_records(run_id="test-run-4")
        assert len(records) == 1
        assert records[0]["success"] is False
        assert records[0]["error_type"] == "RuntimeError"
        clear_trace_context()


class TestTraceCollectorPersistence:
    def test_file_persistence(self, tmp_path):
        collector = get_trace_collector()
        collector.set_file_path(tmp_path / "traces.jsonl")
        collector.clear()

        record_llm_call(
            operation="persist_test",
            model="openrouter/test",
            stage="test",
            success=True,
            latency_ms=100.0,
        )

        import json
        lines = (tmp_path / "traces.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["operation"] == "persist_test"
        collector.set_file_path(None)


class TestIntegrationWithPipeline:
    def test_research_agent_tracing(self):
        """Verify DeepResearchAgent uses tracing (integration test)."""
        clear_trace_context()
        set_trace_context(run_id="int-test", job_id="job1", stage="research")
        collector = get_trace_collector()
        collector.clear()

        from seo_aeo_geo_pipeline.research.deep_research import _call_llm
        from unittest.mock import patch, MagicMock

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="test"))]
        mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)

        with patch("litellm.completion", return_value=mock_resp):
            try:
                _call_llm("test prompt", model="openrouter/test", operation="test_research")
            except Exception:
                pass

        records = collector.get_records(run_id="int-test", stage="research")
        assert len(records) >= 1
        assert any(r["stage"] == "research" for r in records)
        clear_trace_context()


class TestNoSecretsInTraces:
    def test_no_api_key_in_records(self):
        clear_trace_context()
        set_trace_context(run_id="secret-test", job_id="job1", stage="test")
        collector = get_trace_collector()
        collector.clear()

        record_llm_call(
            operation="test",
            model="openrouter/test",
            stage="test",
            success=True,
            latency_ms=100.0,
            metadata={"some_key": "some_value"},
        )

        records = collector.get_records(run_id="secret-test")
        import json
        all_text = json.dumps(records)
        # Should not contain common secret patterns
        assert "sk-" not in all_text
        assert "Bearer" not in all_text
        assert "api_key" not in all_text.lower()
        clear_trace_context()