"""Structured LLM call tracing for LiteLLM instrumentation.

Captures per-call observability records correlatable to CATALYST run/job/page.
Thread-safe in-memory collector with optional JSONL file persistence.

Extension point for Langfuse (or any callback sink):
    register_trace_sink(fn)  # fn(record_dict) called for every trace
or
    collector.set_file_path(Path("output/traces/llm_calls.jsonl"))

No secrets, API keys, or full prompts are recorded — only metadata.
"""

from __future__ import annotations

import contextvars
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


# ── Context propagation ──────────────────────────────────────────

current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="")
current_job_id: contextvars.ContextVar[str] = contextvars.ContextVar("job_id", default="")
current_stage: contextvars.ContextVar[str] = contextvars.ContextVar("stage", default="")


def set_trace_context(
    run_id: str = "",
    job_id: str = "",
    stage: str = "",
) -> dict[str, Any]:
    """Set correlatable context for subsequent LLM trace records."""
    if run_id:
        current_run_id.set(run_id)
    if job_id:
        current_job_id.set(job_id)
    if stage:
        current_stage.set(stage)
    return get_trace_context()


def get_trace_context() -> dict[str, str]:
    return {
        "run_id": current_run_id.get(),
        "job_id": current_job_id.get(),
        "stage": current_stage.get(),
    }


def clear_trace_context() -> None:
    current_run_id.set("")
    current_job_id.set("")
    current_stage.set("")


class trace_context:
    """Context manager for setting trace context temporarily.

    Usage:
        with trace_context(run_id="r1", job_id="j1", stage="research"):
            ...llm calls...
    """

    def __init__(self, run_id: str = "", job_id: str = "", stage: str = ""):
        self._run_id = run_id
        self._job_id = job_id
        self._stage = stage
        self._tokens: list = []

    def __enter__(self):
        if self._run_id:
            self._tokens.append((current_run_id, current_run_id.set(self._run_id)))
        if self._job_id:
            self._tokens.append((current_job_id, current_job_id.set(self._job_id)))
        if self._stage:
            self._tokens.append((current_stage, current_stage.set(self._stage)))
        return self

    def __exit__(self, *args):
        for var, token in reversed(self._tokens):
            var.reset(token)
        return False


# ── Trace record ─────────────────────────────────────────────────

@dataclass
class LLMTraceRecord:
    """Structured record for a single LLM call."""

    trace_id: str
    run_id: str
    job_id: str
    stage: str
    operation: str
    model: str
    provider: str
    started_at: str
    ended_at: str
    latency_ms: float
    success: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_provider(model: str) -> str:
    """Extract provider prefix from model string (e.g. 'openrouter/...' → 'openrouter')."""
    if "/" in model:
        return model.split("/", 1)[0]
    return model


def _usage_from_response(response: Any) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Extract token counts from a LiteLLM response object."""
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None, None, None
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        total = getattr(usage, "total_tokens", None)
        if total is None and prompt is not None and completion is not None:
            total = prompt + completion
        return prompt, completion, total
    except Exception:
        return None, None, None


def _cost_from_response(response: Any) -> Optional[float]:
    """Extract cost from LiteLLM response if exposed."""
    try:
        cost = getattr(response, "_hidden_params", None)
        if isinstance(cost, dict):
            return cost.get("response_cost")
        # LiteLLM sometimes sets response.cost directly on newer versions
        return getattr(response, "cost", None)
    except Exception:
        return None


# ── Collector ────────────────────────────────────────────────────

TraceSink = Callable[[dict], None]


class LLMTraceCollector:
    """Thread-safe in-memory trace collector with optional file persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[LLMTraceRecord] = []
        self._sinks: list[TraceSink] = []
        self._file_path: Optional[Path] = None
        self._max_memory = 1000

    def set_file_path(self, path: Path | str | None) -> None:
        """Enable JSONL persistence to the given path. Pass None to disable."""
        if path is None:
            self._file_path = None
            return
        self._file_path = Path(path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def register_sink(self, sink: TraceSink) -> None:
        """Register an external sink (e.g. Langfuse adapter)."""
        with self._lock:
            self._sinks.append(sink)

    def record(self, rec: LLMTraceRecord) -> None:
        """Store a trace record and notify sinks."""
        with self._lock:
            self._records.append(rec)
            if len(self._records) > self._max_memory:
                self._records = self._records[-self._max_memory:]
            sinks = list(self._sinks)
            file_path = self._file_path
        data = rec.to_dict()
        for sink in sinks:
            try:
                sink(data)
            except Exception:
                pass  # sinks must not break the application
        if file_path is not None:
            try:
                with open(file_path, "a") as f:
                    f.write(json.dumps(data, default=str) + "\n")
            except Exception:
                pass

    def get_records(
        self,
        run_id: str | None = None,
        job_id: str | None = None,
        stage: str | None = None,
    ) -> list[dict]:
        """Return trace records, optionally filtered."""
        with self._lock:
            records = list(self._records)
        out = []
        for r in records:
            if run_id is not None and r.run_id != run_id:
                continue
            if job_id is not None and r.job_id != job_id:
                continue
            if stage is not None and r.stage != stage:
                continue
            out.append(r.to_dict())
        return out

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


# Global singleton collector
_collector = LLMTraceCollector()


def get_trace_collector() -> LLMTraceCollector:
    return _collector


def register_trace_sink(sink: TraceSink) -> None:
    """Register a trace sink (extension point for Langfuse etc.)."""
    _collector.register_sink(sink)


def record_llm_call(
    *,
    operation: str,
    model: str,
    stage: str = "",
    success: bool = True,
    error: Optional[Exception] = None,
    retry_count: int = 0,
    response: Any = None,
    latency_ms: float = 0.0,
    metadata: Optional[dict] = None,
) -> dict:
    """Record an LLM call trace. Safe to call from any LiteLLM wrapper.

    Never records prompts, API keys, or response content — only metadata.
    """
    ctx = get_trace_context()
    now = datetime.now(timezone.utc).isoformat()
    started = datetime.fromtimestamp(
        (time.time() - latency_ms / 1000.0), tz=timezone.utc
    ).isoformat()

    input_tokens, output_tokens, total_tokens = (None, None, None)
    cost = None
    if response is not None:
        input_tokens, output_tokens, total_tokens = _usage_from_response(response)
        cost = _cost_from_response(response)

    error_type = None
    error_message = None
    if error is not None:
        error_type = type(error).__name__
        # Truncate error message; never include full prompts/keys
        error_message = str(error)[:300]

    rec = LLMTraceRecord(
        trace_id=uuid.uuid4().hex[:16],
        run_id=ctx.get("run_id", ""),
        job_id=ctx.get("job_id", ""),
        stage=stage or ctx.get("stage", ""),
        operation=operation,
        model=model,
        provider=_extract_provider(model),
        started_at=started,
        ended_at=now,
        latency_ms=round(latency_ms, 2),
        success=success,
        error_type=error_type,
        error_message=error_message,
        retry_count=retry_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=cost,
        metadata=metadata or {},
    )
    _collector.record(rec)
    return rec.to_dict()


def instrument_litellm_call(
    litellm_completion_fn: Callable,
    *,
    operation: str,
    stage: str = "",
    **call_kwargs,
) -> Any:
    """Wrap a litellm.completion call with tracing.

    Args:
        litellm_completion_fn: callable that invokes litellm.completion(**kwargs)
        operation: logical operation name (e.g. 'plan_research', 'generate_article')
        stage: pipeline stage (e.g. 'research', 'generation')
        **call_kwargs: forwarded to litellm_completion_fn (must include 'model')

    Returns:
        The LiteLLM response object (unchanged behavior).
    """
    model = call_kwargs.get("model", "unknown")
    start = time.monotonic()
    try:
        response = litellm_completion_fn(**call_kwargs)
        latency = (time.monotonic() - start) * 1000
        record_llm_call(
            operation=operation,
            model=model,
            stage=stage,
            success=True,
            response=response,
            latency_ms=latency,
        )
        return response
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        record_llm_call(
            operation=operation,
            model=model,
            stage=stage,
            success=False,
            error=e,
            latency_ms=latency,
        )
        raise
