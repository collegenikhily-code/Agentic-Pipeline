"""Competitor intelligence module.

Bridges SE Ranking discovery data with crawled competitor content,
producing IntelligenceRecords ready for Dify ingestion.

Core principle: after discovery/intelligence dataset is created and stored,
downstream production must NOT need to call SE Ranking.
"""

from .models import IntelligenceRecord, SerankingMeta
from .mapper import (
    CrawledPageContent,
    DiscoveryArtifacts,
    IntelligenceMapper,
    load_crawled_pages_from_proof,
)
from .ingest import DifyIngestionClient, IngestionResult, IngestionSummary

__all__ = [
    "IntelligenceRecord",
    "SerankingMeta",
    "DiscoveryArtifacts",
    "CrawledPageContent",
    "IntelligenceMapper",
    "load_crawled_pages_from_proof",
    "DifyIngestionClient",
    "IngestionResult",
    "IngestionSummary",
]
