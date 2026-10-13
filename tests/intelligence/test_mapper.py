"""Tests for DiscoveryArtifacts loading and IntelligenceMapper."""

import json
import tempfile
from pathlib import Path

import pytest

from seo_aeo_geo_pipeline.intelligence.mapper import (
    CrawledPageContent,
    DiscoveryArtifacts,
    IntelligenceMapper,
)


SAMPLE_OBSERVATIONS = [
    {
        "keyword": "meta ads mcp",
        "search_volume": 5000,
        "difficulty": 45.0,
        "cpc": 3.5,
        "competition": 0.6,
        "intent": "commercial",
        "serp_features": ["featured_snippets"],
        "ranking_domain": "blend-ai.com",
        "ranking_url": "https://blend-ai.com/mcp",
        "ranking_position": 2,
        "our_position": None,
        "source": "se_ranking",
    },
    {
        "keyword": "facebook business manager",
        "search_volume": 18100,
        "difficulty": 96.0,
        "cpc": 2.0,
        "competition": 0.8,
        "intent": "informational",
        "serp_features": [],
        "ranking_domain": "get-ryze.ai",
        "ranking_url": "https://www.get-ryze.ai/blog/facebook-busines-manager",
        "ranking_position": 27,
        "our_position": None,
        "source": "se_ranking",
    },
]

SAMPLE_CLUSTERS = [
    {
        "cluster_id": "kc-meta-ads-mcp-abc123",
        "primary_keyword": "meta ads mcp",
        "keywords": ["meta ads mcp", "meta ads mcp server"],
        "dominant_intent": "commercial",
        "total_search_volume": 5000,
        "avg_difficulty": 45.0,
        "competitor_pages": ["https://blend-ai.com/mcp"],
        "supporting_questions": [],
        "serp_features": ["featured_snippets"],
    },
    {
        "cluster_id": "kc-facebook-business-manager-def456",
        "primary_keyword": "facebook business manager",
        "keywords": ["facebook business manager"],
        "dominant_intent": "informational",
        "total_search_volume": 18100,
        "avg_difficulty": 96.0,
        "competitor_pages": ["https://www.get-ryze.ai/blog/facebook-busines-manager"],
        "supporting_questions": [],
        "serp_features": [],
    },
]

SAMPLE_COMPETITOR_PAGES = [
    {
        "domain": "blend-ai.com",
        "url": "https://blend-ai.com/mcp",
        "keywords": ["meta ads mcp"],
        "ranking_positions": {"meta ads mcp": 2},
        "avg_volume": 5000.0,
        "avg_difficulty": 45.0,
        "total_traffic": 0.0,
    },
    {
        "domain": "get-ryze.ai",
        "url": "https://www.get-ryze.ai/blog/facebook-busines-manager",
        "keywords": ["facebook business manager"],
        "ranking_positions": {"facebook business manager": 27},
        "avg_volume": 18100.0,
        "avg_difficulty": 96.0,
        "total_traffic": 0.0,
    },
]

SAMPLE_OPPORTUNITIES = [
    {
        "opportunity_id": "opp-meta-ads-mcp-abc123",
        "primary_keyword": "meta ads mcp",
        "secondary_keywords": [],
        "intent": "commercial",
        "search_volume": 5000,
        "difficulty": 45.0,
        "competitor_pages": ["https://blend-ai.com/mcp"],
        "questions": [],
        "serp_features": ["featured_snippets"],
        "recommended_page_type": "product",
        "recommended_slug": "meta-ads-mcp",
        "opportunity_reason": "High volume, low competition",
    },
]

SAMPLE_CRAWLED_PAGES = [
    {
        "competitor": "Blend MCP",
        "domain": "blend-ai.com",
        "url": "https://blend-ai.com/mcp",
        "title": "Blend MCP - Meta Ads Integration",
        "description": "MCP server for Meta Ads",
        "page_type": "product",
        "headings": ["Overview", "Features", "Setup"],
        "main_content": "Blend MCP provides Meta Ads integration via MCP protocol.",
        "faq": [{"question": "What is MCP?", "answer": "Model Context Protocol"}],
        "word_count": 250,
        "content_hash": "abc123def456",
        "http_status": 200,
        "error": None,
    },
]


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


@pytest.fixture
def discovery_dir(tmp_path):
    raw = tmp_path / "raw"
    _write_json(raw / "keyword_observations.json", SAMPLE_OBSERVATIONS)
    _write_json(raw / "keyword_clusters.json", SAMPLE_CLUSTERS)
    _write_json(raw / "competitor_pages.json", SAMPLE_COMPETITOR_PAGES)
    _write_json(raw / "page_opportunities.json", SAMPLE_OPPORTUNITIES)
    return tmp_path


@pytest.fixture
def crawled_file(tmp_path):
    path = tmp_path / "crawl_results.json"
    _write_json(path, SAMPLE_CRAWLED_PAGES)
    return path


class TestDiscoveryArtifacts:
    def test_load(self, discovery_dir):
        artifacts = DiscoveryArtifacts.load(discovery_dir)
        assert len(artifacts.keyword_observations) == 2
        assert len(artifacts.keyword_clusters) == 2
        assert len(artifacts.competitor_pages) == 2
        assert len(artifacts.page_opportunities) == 1

    def test_load_missing_dir(self, tmp_path):
        artifacts = DiscoveryArtifacts.load(tmp_path / "nonexistent")
        assert len(artifacts.keyword_observations) == 0
        assert len(artifacts.keyword_clusters) == 0

    def test_load_missing_files(self, tmp_path):
        artifacts = DiscoveryArtifacts.load(tmp_path)
        assert len(artifacts.keyword_observations) == 0


class TestCrawledPageContent:
    def test_load_list(self, crawled_file):
        crawled = CrawledPageContent.load(crawled_file)
        assert len(crawled.pages) == 1
        assert crawled.pages[0]["url"] == "https://blend-ai.com/mcp"

    def test_load_missing(self, tmp_path):
        crawled = CrawledPageContent.load(tmp_path / "missing.json")
        assert len(crawled.pages) == 0

    def test_by_url(self, crawled_file):
        crawled = CrawledPageContent.load(crawled_file)
        index = crawled.by_url()
        assert "https://blend-ai.com/mcp" in index


class TestIntelligenceMapper:
    def test_map_all_no_crawled(self, discovery_dir):
        artifacts = DiscoveryArtifacts.load(discovery_dir)
        mapper = IntelligenceMapper(artifacts)
        records = mapper.map_all()

        # Should map both URLs from competitor_pages + observations
        assert len(records) >= 2

        # Verify SE Ranking metadata is attached
        urls = {r.url for r in records}
        assert "https://blend-ai.com/mcp" in urls
        assert "https://www.get-ryze.ai/blog/facebook-busines-manager" in urls

        # Verify seranking metadata
        blend_record = next(r for r in records if r.url == "https://blend-ai.com/mcp")
        assert blend_record.seranking.keyword == "meta ads mcp"
        assert blend_record.seranking.cluster_id == "kc-meta-ads-mcp-abc123"
        assert blend_record.seranking.intent == "commercial"
        assert blend_record.seranking.search_volume == 5000
        assert blend_record.seranking.ranking_position == 2
        assert blend_record.source == "seranking_competitor"

    def test_map_all_with_crawled(self, discovery_dir, crawled_file):
        artifacts = DiscoveryArtifacts.load(discovery_dir)
        crawled = CrawledPageContent.load(crawled_file)
        mapper = IntelligenceMapper(artifacts, crawled)
        records = mapper.map_all()

        blend_record = next(r for r in records if r.url == "https://blend-ai.com/mcp")
        assert blend_record.title == "Blend MCP - Meta Ads Integration"
        assert blend_record.content == "Blend MCP provides Meta Ads integration via MCP protocol."
        assert blend_record.page_type == "product"
        assert blend_record.word_count == 250
        assert blend_record.content_hash == "abc123def456"

    def test_map_all_max_records(self, discovery_dir):
        artifacts = DiscoveryArtifacts.load(discovery_dir)
        mapper = IntelligenceMapper(artifacts)
        records = mapper.map_all(max_records=1)
        assert len(records) == 1

    def test_map_all_require_content(self, discovery_dir):
        artifacts = DiscoveryArtifacts.load(discovery_dir)
        mapper = IntelligenceMapper(artifacts)
        records = mapper.map_all(require_content=True)
        # No crawled content available → all filtered out
        assert len(records) == 0

    def test_map_one_no_metadata(self):
        artifacts = DiscoveryArtifacts([])
        mapper = IntelligenceMapper(artifacts)
        record = mapper.map_one(
            url="https://unknown.com/page",
            competitor_domain="unknown.com",
        )
        assert record is None

    def test_traceability(self, discovery_dir):
        """Every produced record must have SE Ranking metadata."""
        artifacts = DiscoveryArtifacts.load(discovery_dir)
        mapper = IntelligenceMapper(artifacts)
        records = mapper.map_all()

        for record in records:
            has_metadata = (
                record.seranking.keyword
                or record.seranking.cluster_id
                or record.seranking.intent
            )
            assert has_metadata, f"Record {record.url} lacks SE Ranking metadata"
