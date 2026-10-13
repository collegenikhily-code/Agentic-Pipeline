"""Research agents for the SEO + AEO + GEO pipeline.

M1: ResearchAgent (deterministic heuristic)
M2: DeepResearchAgent (LLM-powered via litellm) - see research.deep_research
"""

from seo_aeo_geo_pipeline.research.agents.research_agent import ResearchAgent, create_agent  # noqa: F401

__all__ = ["ResearchAgent", "create_agent"]
