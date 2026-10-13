"""Adapter wiring CATALYST PageJob to research agents.

Supports both:
  - ResearchAgent (deterministic/heuristic, M1)
  - DeepResearchAgent (LLM-powered, M2)

The adapter is the smallest bridge between CATALYST's research_fn protocol
and the research agent interface.
"""

from __future__ import annotations

import logging
from typing import Any, Union

from seo_aeo_geo_pipeline.models import PageJob
from seo_aeo_geo_pipeline.research.agents import ResearchAgent
from seo_aeo_geo_pipeline.research.deep_research import DeepResearchAgent
from seo_aeo_geo_pipeline.observability.llm_trace import trace_context

logger = logging.getLogger(__name__)


def create_research_fn(agent: Union[ResearchAgent, DeepResearchAgent, None] = None):
    """Create a research_fn compatible with Catalyst.run().

    Args:
        agent: ResearchAgent or DeepResearchAgent instance.
               If None, creates a default DeepResearchAgent.

    Returns:
        A callable that accepts a PageJob and returns the research result dict.
               Raises RuntimeError if research is partial/incomplete (retryable).
    """
    if agent is None:
        agent = DeepResearchAgent()

    def research_fn(job: PageJob) -> dict[str, Any]:
        with trace_context(job_id=job.job_id, stage="research"):
            result = agent.run_full_cycle(
                keyword=job.keyword,
                intent=job.intent,
                opportunity_id=1,
            )

        # Check completion status — partial research is retryable, not success
        snapshot = result.get("snapshot", {})
        completion_status = snapshot.get("completion_status", "complete")
        if completion_status != "complete":
            raise RuntimeError(
                f"Research incomplete: {completion_status}. "
                f"Questions answered: {snapshot.get('questions_answered', [])}. "
                f"Retryable."
            )

        return result

    return research_fn
