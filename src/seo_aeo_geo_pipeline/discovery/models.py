"""Internal data models for the Discovery layer.

These models are independent of any external API schema.
SE Ranking responses are normalized into these types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KeywordObservation:
    """A single keyword signal observed via SE Ranking or derived from it."""

    keyword: str
    search_volume: int = 0
    difficulty: int = 0
    cpc: float = 0.0
    competition: float = 0.0
    intent: str = ""
    serp_features: list[str] = field(default_factory=list)
    ranking_domain: str = ""
    ranking_url: str = ""
    ranking_position: Optional[int] = None
    our_position: Optional[int] = None
    source: str = "se_ranking"

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "search_volume": self.search_volume,
            "difficulty": self.difficulty,
            "cpc": self.cpc,
            "competition": self.competition,
            "intent": self.intent,
            "serp_features": self.serp_features,
            "ranking_domain": self.ranking_domain,
            "ranking_url": self.ranking_url,
            "ranking_position": self.ranking_position,
            "our_position": self.our_position,
            "source": self.source,
        }


@dataclass
class CompetitorPage:
    """A competitor URL with its associated keywords and metrics."""

    domain: str
    url: str
    keywords: list[str] = field(default_factory=list)
    ranking_positions: dict[str, int] = field(default_factory=dict)
    avg_volume: float = 0.0
    avg_difficulty: float = 0.0
    total_traffic: float = 0.0

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "url": self.url,
            "keywords": self.keywords,
            "ranking_positions": self.ranking_positions,
            "avg_volume": self.avg_volume,
            "avg_difficulty": self.avg_difficulty,
            "total_traffic": self.total_traffic,
        }


@dataclass
class KeywordCluster:
    """A group of keywords sharing the same search intent and page opportunity."""

    cluster_id: str
    primary_keyword: str
    keywords: list[str] = field(default_factory=list)
    dominant_intent: str = ""
    total_search_volume: int = 0
    avg_difficulty: float = 0.0
    competitor_pages: list[str] = field(default_factory=list)
    supporting_questions: list[str] = field(default_factory=list)
    serp_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "primary_keyword": self.primary_keyword,
            "keywords": self.keywords,
            "dominant_intent": self.dominant_intent,
            "total_search_volume": self.total_search_volume,
            "avg_difficulty": self.avg_difficulty,
            "competitor_pages": self.competitor_pages,
            "supporting_questions": self.supporting_questions,
            "serp_features": self.serp_features,
        }


@dataclass
class PageOpportunity:
    """A potential page to create, derived from a keyword cluster."""

    opportunity_id: str
    primary_keyword: str
    secondary_keywords: list[str] = field(default_factory=list)
    intent: str = ""
    search_volume: int = 0
    difficulty: float = 0.0
    competitor_pages: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    serp_features: list[str] = field(default_factory=list)
    recommended_page_type: str = ""
    recommended_slug: str = ""
    opportunity_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "opportunity_id": self.opportunity_id,
            "primary_keyword": self.primary_keyword,
            "secondary_keywords": self.secondary_keywords,
            "intent": self.intent,
            "search_volume": self.search_volume,
            "difficulty": self.difficulty,
            "competitor_pages": self.competitor_pages,
            "questions": self.questions,
            "serp_features": self.serp_features,
            "recommended_page_type": self.recommended_page_type,
            "recommended_slug": self.recommended_slug,
            "opportunity_reason": self.opportunity_reason,
        }
