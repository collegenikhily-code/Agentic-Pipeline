"""LetterTrace integration for pipeline observability.

Provides a trace sink that forwards LLMTraceRecord to LetterTrace.
Uses a generic HTTP API for maximum compatibility.

Configuration via environment variables:
    LETTERTRACE_API_KEY
    LETTERTRACE_BASE_URL (optional, default: https://api.lettertrace.ai)
    LETTERTRACE_PROJECT_ID (optional)

If not configured, the sink is a no-op (graceful degradation).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import requests

from seo_aeo_geo_pipeline.observability.llm_trace import LLMTraceRecord

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.lettertrace.ai"


class LetterTraceSink:
    """LetterTrace trace sink for pipeline observability.

    Forwards traces to LetterTrace using a generic REST API.
    Gracefully degrades if LetterTrace is not configured or unavailable.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        project_id: Optional[str] = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.environ.get("LETTERTRACE_API_KEY", "")
        self.base_url = (base_url or os.environ.get("LETTERTRACE_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self.project_id = project_id or os.environ.get("LETTERTRACE_PROJECT_ID", "")
        self.timeout = timeout
        self._session: Optional[requests.Session] = None
        self._initialized = False

    @property
    def is_configured(self) -> bool:
        """Check if LetterTrace credentials are available."""
        return bool(self.api_key)

    @property
    def is_available(self) -> bool:
        """Check if LetterTrace is configured."""
        return self.is_configured

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            if self.api_key:
                self._session.headers.update({
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                })
        return self._session

    def _ensure_client(self) -> bool:
        """Verify LetterTrace connectivity."""
        if self._initialized:
            return self._session is not None

        self._initialized = True

        if not self.is_configured:
            logger.debug("LetterTrace API key not configured - tracing disabled")
            return False

        try:
            session = self._get_session()
            # Test connectivity with a health check endpoint
            health_endpoint = f"{self.base_url}/health"
            resp = session.get(health_endpoint, timeout=self.timeout)
            if resp.status_code == 200:
                logger.info("LetterTrace client initialized successfully")
                return True
            else:
                logger.warning(f"LetterTrace health check returned {resp.status_code}")
                self._session = None
                return False
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"LetterTrace connection failed: {e}")
            self._session = None
            return False
        except requests.exceptions.Timeout as e:
            logger.warning(f"LetterTrace health check timed out: {e}")
            self._session = None
            return False
        except Exception as e:
            logger.warning(f"LetterTrace initialization failed: {e}")
            self._session = None
            return False

    def __call__(self, trace_data: dict) -> None:
        """Sink interface: receive a trace record dict and forward to LetterTrace.

        This method is called by LLMTraceCollector for each trace record.
        Never raises - failures are logged and swallowed.
        """
        if not self._ensure_client() or self._session is None:
            return

        try:
            self._send_trace(trace_data)
        except Exception as e:
            logger.warning(f"LetterTrace trace send failed: {e}")

    def _send_trace(self, trace_data: dict) -> None:
        """Send a single trace to LetterTrace."""
        if self._session is None:
            return

        # Map our trace fields to LetterTrace event format
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

        # Build LetterTrace event payload
        payload = {
            "trace_id": trace_id,
            "run_id": run_id,
            "job_id": job_id,
            "stage": stage,
            "operation": operation,
            "model": model,
            "provider": provider,
            "started_at": started_at,
            "ended_at": ended_at,
            "latency_ms": latency_ms,
            "success": success,
            "error_type": error_type,
            "error_message": error_message,
            "retry_count": retry_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost": cost,
            "metadata": metadata,
            "project_id": self.project_id,
            "timestamp": ended_at,
        }

        endpoint = f"{self.base_url}/v1/traces"
        try:
            resp = self._session.post(endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text[:500] if e.response is not None else ""
            logger.warning(f"LetterTrace HTTP error {status}: {body}")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"LetterTrace connection failed: {e}")
            raise
        except requests.exceptions.Timeout as e:
            logger.warning(f"LetterTrace request timed out: {e}")
            raise

    def flush(self) -> None:
        """Flush any pending traces (no-op for HTTP-based sink)."""
        pass

    def shutdown(self) -> None:
        """Shutdown the LetterTrace client."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception as e:
                logger.warning(f"LetterTrace shutdown failed: {e}")
            self._session = None


def create_lettertrace_sink(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Optional[LetterTraceSink]:
    """Factory function to create a LetterTraceSink.

    Returns None if LetterTrace is not configured.
    This allows graceful degradation.
    """
    sink = LetterTraceSink(api_key=api_key, base_url=base_url, project_id=project_id)
    if not sink.is_configured:
        logger.debug("LetterTrace not configured - set LETTERTRACE_API_KEY")
        return None

    return sink


def register_lettertrace_sink(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bool:
    """Register LetterTrace sink with the global trace collector.

    Returns True if sink was registered, False if not configured.
    """
    from seo_aeo_geo_pipeline.observability.llm_trace import register_trace_sink

    sink = create_lettertrace_sink(api_key, base_url, project_id)
    if sink is None:
        return False

    register_trace_sink(sink)
    logger.info("LetterTrace sink registered successfully")
    return True


def get_lettertrace_status() -> dict:
    """Get LetterTrace integration status for reporting."""
    return {
        "configured": bool(os.environ.get("LETTERTRACE_API_KEY")),
        "base_url": os.environ.get("LETTERTRACE_BASE_URL", _DEFAULT_BASE_URL),
        "project_id": os.environ.get("LETTERTRACE_PROJECT_ID", ""),
    }