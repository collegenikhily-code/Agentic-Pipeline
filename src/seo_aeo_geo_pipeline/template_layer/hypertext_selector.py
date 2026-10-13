"""HyperText Template Selector Adapter.

Provides a unified interface for template selection that can integrate with
HyperText (external template selection service) when available, with a
deterministic fallback to the internal TemplateSelector.

Architecture:
- HyperTextSelectorAdapter: Main interface, delegates to HyperText when configured
- HyperTextClient: Thin HTTP client for HyperText API (if credentials provided)
- TemplateSelectorFallback: Deterministic internal selector (existing TemplateSelector)

The adapter never generates content. It only selects a template name that
must resolve to a TemplateSpec in the existing TemplateRegistry.

If HyperText is unavailable/unconfigured:
- Falls back to internal TemplateSelector
- Records fallback status in selection result
- Does NOT fabricate HyperText responses
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin

import requests

from .template_registry import TemplateRegistry, TemplateSpec
from .template_selector import TemplateSelector
from ..config import Settings

logger = logging.getLogger(__name__)

# HyperText API configuration (set via environment variables)
HYPERTEXT_API_KEY = os.environ.get("HYPERTEXT_API_KEY", "")
HYPERTEXT_BASE_URL = os.environ.get("HYPERTEXT_BASE_URL", "https://api.hypertext.ai").rstrip("/")
HYPERTEXT_TEMPLATE_SELECT_ENDPOINT = "/v1/templates/select"


@dataclass
class HyperTextSelectionInput:
    """Input payload for HyperText template selection request."""
    keyword: str
    intent: str
    page_type: str
    content_type: str = ""
    target_audience: str = ""
    aeo_geo_requirements: list[str] = field(default_factory=list)
    schema_markup_needs: list[str] = field(default_factory=list)
    differentiation_strategy: str = ""
    competing_analysis: list[dict] = field(default_factory=list)
    questions_answered: list[str] = field(default_factory=list)
    research_sources_count: int = 0
    completion_status: str = "complete"


@dataclass
class HyperTextSelectionResult:
    """Result from template selection (HyperText or fallback)."""
    template_name: str
    template_family: str
    confidence: float
    source: str  # "hypertext" | "fallback"
    fallback_reason: Optional[str] = None
    hypertext_request_id: Optional[str] = None
    hypertext_latency_ms: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class TemplateSelectionContext:
    """Full context for template selection, built from research + job data."""
    job_id: str
    run_id: str
    keyword: str
    intent: str
    page_type: str
    content_type: str
    target_audience: str
    aeo_geo_requirements: list[str]
    schema_markup_needs: list[str]
    differentiation_strategy: str
    competing_analysis: list[dict]
    questions_answered: list[str]
    research_sources_count: int
    completion_status: str


class HyperTextClient:
    """Thin HTTP client for HyperText Template Selection API.

    Expected API contract (to be confirmed with HyperText team):
    POST {base_url}/v1/templates/select
    Headers: Authorization: Bearer {api_key}, Content-Type: application/json
    Body: HyperTextSelectionInput (as JSON)
    Response: { "template_name": str, "template_family": str, "confidence": float, "request_id": str }
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        self.api_key = api_key or HYPERTEXT_API_KEY
        self.base_url = (base_url or HYPERTEXT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            if self.api_key:
                self._session.headers.update({
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                })
        return self._session

    def select_template(self, input_data: HyperTextSelectionInput) -> HyperTextSelectionResult:
        """Call HyperText API for template selection.

        Returns HyperTextSelectionResult with source="hypertext" on success.
        Raises exception on failure (caller handles fallback).
        """
        if not self.is_configured:
            raise RuntimeError("HyperText not configured: HYPERTEXT_API_KEY not set")

        session = self._get_session()
        endpoint = urljoin(self.base_url + "/", HYPERTEXT_TEMPLATE_SELECT_ENDPOINT.lstrip("/"))

        payload = {
            "keyword": input_data.keyword,
            "intent": input_data.intent,
            "page_type": input_data.page_type,
            "content_type": input_data.content_type,
            "target_audience": input_data.target_audience,
            "aeo_geo_requirements": input_data.aeo_geo_requirements,
            "schema_markup_needs": input_data.schema_markup_needs,
            "differentiation_strategy": input_data.differentiation_strategy,
            "competing_analysis": input_data.competing_analysis,
            "questions_answered": input_data.questions_answered,
            "research_sources_count": input_data.research_sources_count,
            "completion_status": input_data.completion_status,
        }

        start = time.monotonic()
        try:
            resp = session.post(endpoint, json=payload, timeout=self.timeout)
            latency_ms = (time.monotonic() - start) * 1000
            resp.raise_for_status()
            data = resp.json()

            # Validate response has required fields
            template_name = data.get("template_name")
            template_family = data.get("template_family", "")
            confidence = float(data.get("confidence", 0.0))
            request_id = data.get("request_id")

            if not template_name:
                raise ValueError("HyperText response missing 'template_name'")

            return HyperTextSelectionResult(
                template_name=template_name,
                template_family=template_family,
                confidence=confidence,
                source="hypertext",
                hypertext_request_id=request_id,
                hypertext_latency_ms=latency_ms,
                metadata={"raw_response": data},
            )

        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"HyperText connection failed: {e}")
        except requests.exceptions.Timeout as e:
            raise RuntimeError(f"HyperText request timed out: {e}")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            body = e.response.text[:500] if e.response is not None else ""
            raise RuntimeError(f"HyperText HTTP error {status}: {body}")
        except ValueError:
            raise  # Re-raise validation errors (e.g., missing template_name)
        except Exception as e:
            raise RuntimeError(f"HyperText selection failed: {e}")


class TemplateSelectorFallback:
    """Deterministic fallback using internal TemplateSelector.

    This is the existing TemplateSelector logic, exposed as a fallback
    with explicit source="fallback" tracking.
    """

    def __init__(self, registry: TemplateRegistry, config: Settings) -> None:
        self.selector = TemplateSelector(registry, config)

    def select(self, context: TemplateSelectionContext) -> HyperTextSelectionResult:
        """Select template using internal TemplateSelector."""
        # Map research page_type to selector page_type
        page_type = context.page_type

        # Build a minimal page_spec dict for the selector
        page_spec = {
            "page_type": page_type,
            "keyword": context.keyword,
            "intent": context.intent,
        }

        spec = self.selector.select_for_page_spec(page_spec)

        if spec is None:
            # Ultimate fallback: comparison-guide
            spec = self.selector.registry.get("comparison_guide_spec")
            if spec is None:
                specs = self.selector.registry.list_all()
                spec = specs[0] if specs else None

        if spec is None:
            raise RuntimeError("No templates registered in TemplateRegistry")

        return HyperTextSelectionResult(
            template_name=spec.name,
            template_family=spec.family,
            confidence=0.9,  # High confidence in deterministic selection
            source="fallback",
            fallback_reason="HyperText unavailable or failed",
            metadata={"selector_page_type": page_type},
        )


class HyperTextSelectorAdapter:
    """Unified template selection adapter.

    Usage:
        adapter = HyperTextSelectorAdapter(registry, config)
        result = adapter.select(context)

    The adapter:
    1. Tries HyperText if configured and available
    2. Falls back to internal TemplateSelector on any failure
    3. Returns HyperTextSelectionResult with source tracking
    4. Validates selected template exists in TemplateRegistry
    """

    def __init__(
        self,
        registry: TemplateRegistry,
        config: Settings,
        hypertext_client: Optional[HyperTextClient] = None,
    ) -> None:
        self.registry = registry
        self.config = config
        self.hypertext = hypertext_client or HyperTextClient()
        self.fallback = TemplateSelectorFallback(registry, config)

    @property
    def hypertext_configured(self) -> bool:
        return self.hypertext.is_configured

    def select(self, context: TemplateSelectionContext) -> HyperTextSelectionResult:
        """Select template, trying HyperText first then falling back."""
        # Try HyperText if configured
        if self.hypertext_configured:
            try:
                input_data = HyperTextSelectionInput(
                    keyword=context.keyword,
                    intent=context.intent,
                    page_type=context.page_type,
                    content_type=context.content_type,
                    target_audience=context.target_audience,
                    aeo_geo_requirements=context.aeo_geo_requirements,
                    schema_markup_needs=context.schema_markup_needs,
                    differentiation_strategy=context.differentiation_strategy,
                    competing_analysis=context.competing_analysis,
                    questions_answered=context.questions_answered,
                    research_sources_count=context.research_sources_count,
                    completion_status=context.completion_status,
                )
                result = self.hypertext.select_template(input_data)
                logger.info(f"HyperText selected template: {result.template_name} (req_id={result.hypertext_request_id})")

                # Validate against registry
                if not self._validate_template(result.template_name):
                    logger.warning(
                        f"HyperText returned unknown template '{result.template_name}', "
                        f"falling back to internal selector"
                    )
                    return self._fallback_select(context, "hypertext_returned_unknown_template")

                return result

            except Exception as e:
                logger.warning(f"HyperText selection failed: {e}, falling back to internal selector")
                return self._fallback_select(context, f"hypertext_error: {e}")

        # HyperText not configured, use fallback directly
        return self._fallback_select(context, "hypertext_not_configured")

    def _fallback_select(self, context: TemplateSelectionContext, reason: str) -> HyperTextSelectionResult:
        """Execute fallback selection with explicit reason."""
        result = self.fallback.select(context)
        result.fallback_reason = reason
        logger.info(f"Fallback selected template: {result.template_name} (reason: {reason})")
        return result

    def _validate_template(self, template_name: str) -> bool:
        """Check if template exists in registry."""
        return self.registry.get(template_name) is not None

    def select_for_research_snapshot(
        self,
        job_id: str,
        run_id: str,
        snapshot: dict,
    ) -> HyperTextSelectionResult:
        """Convenience method: build context from research snapshot and select."""
        context = TemplateSelectionContext(
            job_id=job_id,
            run_id=run_id,
            keyword=snapshot.get("primary_keyword", ""),
            intent=snapshot.get("intent", "informational"),
            page_type=snapshot.get("page_type_recommendation", "comparison-guide"),
            content_type="article",
            target_audience=snapshot.get("audience_profile", ""),
            aeo_geo_requirements=snapshot.get("aeo_geo_requirements", []),
            schema_markup_needs=snapshot.get("schema_markup_needs", []),
            differentiation_strategy=snapshot.get("differentiation_strategy", ""),
            competing_analysis=snapshot.get("competing_analysis", []),
            questions_answered=snapshot.get("questions_answered", []),
            research_sources_count=snapshot.get("source_count", 0),
            completion_status=snapshot.get("completion_status", "complete"),
        )
        return self.select(context)


def create_hypertext_adapter(registry: TemplateRegistry, config: Settings) -> HyperTextSelectorAdapter:
    """Factory function to create HyperTextSelectorAdapter."""
    return HyperTextSelectorAdapter(registry, config)