"""Langfuse integration for LLM observability.

Provides a trace sink that forwards LLMTraceRecord to Langfuse.
Uses Langfuse's low-level API for maximum compatibility.

Configuration via environment variables:
    LANGFUSE_PUBLIC_KEY
    LANGFUSE_SECRET_KEY
    LANGFUSE_HOST (optional, default: https://cloud.langfuse.com)

If not configured, the sink is a no-op (graceful degradation).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from seo_aeo_geo_pipeline.observability.llm_trace import LLMTraceRecord

logger = logging.getLogger(__name__)

# Check if langfuse is available
try:
    from langfuse import Langfuse
    from langfuse.api.resources.commons.errors.unauthorized_error import UnauthorizedError
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    Langfuse = None  # type: ignore
    UnauthorizedError = Exception  # type: ignore


class LangfuseSink:
    """Langfuse trace sink for LLM call observability.

    Forwards traces to Langfuse using the low-level API.
    Gracefully degrades if Langfuse is not configured or unavailable.
    """

    def __init__(
        self,
        public_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
        flush_interval: float = 5.0,
    ):
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "")
        self.host = host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self.flush_interval = flush_interval
        self._client: Optional[Langfuse] = None
        self._initialized = False

    @property
    def is_configured(self) -> bool:
        """Check if Langfuse credentials are available."""
        return bool(self.public_key) and bool(self.secret_key)

    @property
    def is_available(self) -> bool:
        """Check if Langfuse package is installed and configured."""
        return LANGFUSE_AVAILABLE and self.is_configured

    def _ensure_client(self) -> bool:
        """Initialize Langfuse client if not already done."""
        if self._initialized:
            return self._client is not None

        self._initialized = True

        if not LANGFUSE_AVAILABLE:
            logger.debug("Langfuse package not installed - tracing disabled")
            return False

        if not self.is_configured:
            logger.debug("Langfuse credentials not configured - tracing disabled")
            return False

        try:
            self._client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
                flush_interval=self.flush_interval,
            )
            # Verify connection
            self._client.auth_check()
            logger.info("Langfuse client initialized successfully")
            return True
        except UnauthorizedError:
            logger.warning("Langfuse authentication failed - check credentials")
            self._client = None
            return False
        except Exception as e:
            logger.warning(f"Langfuse initialization failed: {e}")
            self._client = None
            return False

    def __call__(self, trace_data: dict) -> None:
        """Sink interface: receive a trace record dict and forward to Langfuse.

        This method is called by LLMTraceCollector for each trace record.
        Never raises - failures are logged and swallowed.
        """
        if not self._ensure_client() or self._client is None:
            return

        try:
            self._send_trace(trace_data)
        except Exception as e:
            logger.warning(f"Langfuse trace send failed: {e}")

    def _send_trace(self, trace_data: dict) -> None:
        """Send a single trace to Langfuse."""
        if self._client is None:
            return

        # Map our trace fields to Langfuse observation
        # Langfuse expects: name, input, output, metadata, start_time, end_time, etc.
        trace_id = trace_data.get("trace_id", "")
        run_id = trace_data.get("run_id", "")
        job_id = trace_data.get("job_id", "")
        stage = trace_data.get("stage", "")
        operation = trace_data.get("operation", "")
        model = trace_data.get("model", "")
        provider = trace_data.get("provider", "")
        started_at = trace_data.get("started_at", "")
        ended_at = trace_data.get("ended_at", "")
        latency_ms = trace_data.get("latency_ms", 0.0)
        success = trace_data.get("success", True)
        error_type = trace_data.get("error_type")
        error_message = trace_data.get("error_message")
        retry_count = trace_data.get("retry_count", 0)
        input_tokens = trace_data.get("input_tokens")
        output_tokens = trace_data.get("output_tokens")
        total_tokens = trace_data.get("total_tokens")
        cost = trace_data.get("cost")
        metadata = trace_data.get("metadata", {})

        # Build Langfuse observation
        # Use generation for LLM calls
        self._client.generation(
            id=trace_id,
            name=operation,
            model=model,
            model_parameters=metadata.get("model_parameters", {}),
            input=metadata.get("input_preview", {}),
            output=metadata.get("output_preview", {}),
            start_time=started_at,
            end_time=ended_at,
            metadata={
                "run_id": run_id,
                "job_id": job_id,
                "stage": stage,
                "provider": provider,
                "latency_ms": latency_ms,
                "success": success,
                "error_type": error_type,
                "error_message": error_message,
                "retry_count": retry_count,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost": cost,
                **metadata,
            },
            usage={
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": total_tokens,
            } if total_tokens is not None else None,
            level="ERROR" if not success else "DEFAULT",
            status_message=error_message if not success else None,
        )

    def flush(self) -> None:
        """Flush any pending traces to Langfuse."""
        if self._client is not None:
            try:
                self._client.flush()
            except Exception as e:
                logger.warning(f"Langfuse flush failed: {e}")

    def shutdown(self) -> None:
        """Shutdown the Langfuse client."""
        if self._client is not None:
            try:
                self._client.shutdown()
            except Exception as e:
                logger.warning(f"Langfuse shutdown failed: {e}")
            self._client = None


def create_langfuse_sink(
    public_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    host: Optional[str] = None,
) -> Optional[LangfuseSink]:
    """Factory function to create a LangfuseSink.

    Returns None if Langfuse is not available or not configured.
    This allows graceful degradation.
    """
    if not LANGFUSE_AVAILABLE:
        logger.debug("Langfuse not available - install 'langfuse' package to enable")
        return None

    sink = LangfuseSink(public_key=public_key, secret_key=secret_key, host=host)
    if not sink.is_configured:
        logger.debug("Langfuse not configured - set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY")
        return None

    return sink


def register_langfuse_sink(
    public_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    host: Optional[str] = None,
) -> bool:
    """Register Langfuse sink with the global trace collector.

    Returns True if sink was registered, False if not available/configured.
    """
    from seo_aeo_geo_pipeline.observability.llm_trace import register_trace_sink

    sink = create_langfuse_sink(public_key, secret_key, host)
    if sink is None:
        return False

    register_trace_sink(sink)
    logger.info("Langfuse sink registered successfully")
    return True


def get_langfuse_status() -> dict:
    """Get Langfuse integration status for reporting."""
    return {
        "available": LANGFUSE_AVAILABLE,
        "configured": bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(os.environ.get("LANGFUSE_SECRET_KEY")),
        "host": os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    }