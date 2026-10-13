"""Intelligence data contract.

Bridges SE Ranking discovery data with crawled competitor content.
Each IntelligenceRecord is a single competitor page enriched with
the SE Ranking metadata that led us to it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SerankingMeta:
    """SE Ranking provenance attached to an intelligence record."""

    keyword: str = ""
    cluster_id: str = ""
    intent: str = ""
    search_volume: int = 0
    difficulty: float = 0.0
    ranking_position: Optional[int] = None


@dataclass
class IntelligenceRecord:
    """A competitor page enriched with SE Ranking discovery metadata.

    This is the canonical record that gets ingested into Dify.
    Content is traceable back to SE Ranking data via the seranking field.
    """

    url: str
    competitor_domain: str
    title: str = ""
    content: str = ""
    page_type: str = ""
    seranking: SerankingMeta = field(default_factory=SerankingMeta)
    source: str = "seranking_competitor"
    collected_at: str = ""
    content_hash: str = ""
    headings: list[str] = field(default_factory=list)
    description: str = ""
    faq: list[dict] = field(default_factory=list)
    word_count: int = 0

    def __post_init__(self):
        if not self.collected_at:
            self.collected_at = datetime.now(timezone.utc).isoformat()
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON storage and Dify ingestion."""
        return {
            "url": self.url,
            "competitor_domain": self.competitor_domain,
            "title": self.title,
            "content": self.content,
            "page_type": self.page_type,
            "seranking": {
                "keyword": self.seranking.keyword,
                "cluster_id": self.seranking.cluster_id,
                "intent": self.seranking.intent,
                "search_volume": self.seranking.search_volume,
                "difficulty": self.seranking.difficulty,
                "ranking_position": self.seranking.ranking_position,
            },
            "source": self.source,
            "collected_at": self.collected_at,
            "content_hash": self.content_hash,
            "headings": self.headings,
            "description": self.description,
            "faq": self.faq,
            "word_count": self.word_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntelligenceRecord":
        """Deserialize from a plain dict."""
        seranking_data = data.get("seranking", {})
        seranking = SerankingMeta(
            keyword=seranking_data.get("keyword", ""),
            cluster_id=seranking_data.get("cluster_id", ""),
            intent=seranking_data.get("intent", ""),
            search_volume=seranking_data.get("search_volume", 0),
            difficulty=seranking_data.get("difficulty", 0.0),
            ranking_position=seranking_data.get("ranking_position"),
        )
        return cls(
            url=data.get("url", ""),
            competitor_domain=data.get("competitor_domain", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            page_type=data.get("page_type", ""),
            seranking=seranking,
            source=data.get("source", "seranking_competitor"),
            collected_at=data.get("collected_at", ""),
            content_hash=data.get("content_hash", ""),
            headings=data.get("headings", []),
            description=data.get("description", ""),
            faq=data.get("faq", []),
            word_count=data.get("word_count", 0),
        )

    def to_dify_text(self) -> str:
        """Render as text suitable for Dify document ingestion.

        Preserves all provenance and metadata in the document body so
        retrieval results remain traceable back to SE Ranking data.
        """
        sk = self.seranking
        lines = [
            f"# {self.title or self.url}",
            "",
            f"URL: {self.url}",
            f"Competitor: {self.competitor_domain}",
            f"Page type: {self.page_type}",
            f"Source: {self.source}",
            f"Collected at: {self.collected_at}",
            f"Content hash: {self.content_hash}",
            "",
            "## SE Ranking Metadata",
            f"Keyword: {sk.keyword}",
            f"Cluster ID: {sk.cluster_id}",
            f"Intent: {sk.intent}",
            f"Search volume: {sk.search_volume}",
            f"Difficulty: {sk.difficulty}",
            f"Ranking position: {sk.ranking_position}",
            "",
        ]
        if self.description:
            lines.extend(["## Description", self.description, ""])
        if self.headings:
            lines.extend(["## Headings"])
            lines.extend(f"- {h}" for h in self.headings)
            lines.append("")
        if self.content:
            lines.extend(["## Content", self.content, ""])
        if self.faq:
            lines.extend(["## FAQ"])
            for item in self.faq:
                q = item.get("question", "")
                a = item.get("answer", "")
                if q:
                    lines.append(f"**Q:** {q}")
                if a:
                    lines.append(f"**A:** {a}")
                lines.append("")
        return "\n".join(lines)
