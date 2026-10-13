"""Observability package — structured LLM call tracing.

Minimal structured trace mechanism. Clean extension point for Langfuse and LetterTrace:
register a trace sink via `register_trace_sink()` and external services
can be wired without changing call sites.
"""

from seo_aeo_geo_pipeline.observability.llm_trace import (
    LLMTraceRecord,
    get_trace_collector,
    record_llm_call,
    register_trace_sink,
    set_trace_context,
    clear_trace_context,
    trace_context,
)
from seo_aeo_geo_pipeline.observability.langfuse_sink import (
    LangfuseSink,
    create_langfuse_sink,
    register_langfuse_sink,
    get_langfuse_status,
)
from seo_aeo_geo_pipeline.observability.lettertrace_sink import (
    LetterTraceSink,
    create_lettertrace_sink,
    register_lettertrace_sink,
    get_lettertrace_status,
)

__all__ = [
    "LLMTraceRecord",
    "get_trace_collector",
    "record_llm_call",
    "register_trace_sink",
    "set_trace_context",
    "clear_trace_context",
    "trace_context",
    "LangfuseSink",
    "create_langfuse_sink",
    "register_langfuse_sink",
    "get_langfuse_status",
    "LetterTraceSink",
    "create_lettertrace_sink",
    "register_lettertrace_sink",
    "get_lettertrace_status",
]