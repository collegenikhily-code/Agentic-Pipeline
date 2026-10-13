"""Research data normalization - M1 contracts only.

Research Provider → normalized research schema → research_snapshot.
Provenance preserved at source/collection level; snapshot provider-agnostic.

M1: Defines the normalized schema contract. Real research collection 
(Marketing Agent OS, OpenSEO, SE Ranking MCP) in M2+.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


# Normalized research schema - what persists in research_snapshot
NormalizedResearch = Dict[str, Any]

# Source provenance record - preserved at individual source level
SourceProvenance = Dict[str, Any]

# Research collection types
COLLECTOR_PSEO_ENGINE = "pseo_engine"
COLLECTOR_MARKETING_AGENT_OS = "marketing_agent_os"
COLLECTOR_OPENSEO = "open-seo"
COLLECTOR_MANUAL = "manual"
COLLECTOR_SE_RANKING_MCP = "seranking_mcp"


def normalize_source(
    source_url: str,
    source_type: str,
    excerpt: str,
    confidence: float,
    collector: str,
    metadata: Optional[dict] = None,
) -> SourceProvenance:
    """Normalize a research source into provenance record.
    
    M1: Creates provenance record with collector-level metadata.
    Real collection (DataForSEO, SerpApi, Reddit, etc.) M2+.
    """
    return {
        "source_url": source_url,
        "source_type": source_type,
        "excerpt": excerpt,
        "confidence": confidence,
        "collector": collector,
        "metadata": metadata or {},
        "normalized_at": "2026-01-01T00:00:00Z",  # placeholder - real timestamp from collection
    }


def create_research_snapshot(
    opportunity_id: int,
    sources: List[SourceProvenance],
    data_hash: str,
    provider: str = "manual",
) -> dict:
    """Create a research snapshot from normalized sources.
    
    M1: Snapshots is provider-agnostic; provenance at source level.
    Real collection M2+.
    """
    return {
        "opportunity_id": opportunity_id,
        "sources": sources,
        "data_hash": data_hash,
        "provider": provider,  # recorded but snapshot itself is agnostic
        "source_count": len(sources),
        "created_at": "2026-01-01T00:00:00Z",
    }