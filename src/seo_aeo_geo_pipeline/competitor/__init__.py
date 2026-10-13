"""Competitor Intelligence subsystem.

Provides controlled competitor page crawling, content extraction,
relevance retrieval, and research-pack generation for the existing
deep research pipeline.

Usage:
    from seo_aeo_geo_pipeline.competitor import CompetitorIntel, CompetitorIntelReadiness

    intel = CompetitorIntel.from_config("config/competitors.yaml")
    pack = intel.build_research_pack("google ads automation")
    readiness = intel.get_readiness("google ads automation")
    # pack is a list of CompetitorEvidence ready for Deep Research
"""

from seo_aeo_geo_pipeline.competitor.intel import (
    CompetitorIntel,
    CompetitorIntelReadiness,
)

__all__ = ["CompetitorIntel", "CompetitorIntelReadiness"]
