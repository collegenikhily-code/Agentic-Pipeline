"""Tests for IntelligenceRecord and SerankingMeta models."""

import pytest
from seo_aeo_geo_pipeline.intelligence.models import IntelligenceRecord, SerankingMeta


class TestSerankingMeta:
    def test_defaults(self):
        meta = SerankingMeta()
        assert meta.keyword == ""
        assert meta.cluster_id == ""
        assert meta.intent == ""
        assert meta.search_volume == 0
        assert meta.difficulty == 0.0
        assert meta.ranking_position is None

    def test_custom_values(self):
        meta = SerankingMeta(
            keyword="test keyword",
            cluster_id="kc-test-123",
            intent="commercial",
            search_volume=1000,
            difficulty=45.0,
            ranking_position=3,
        )
        assert meta.keyword == "test keyword"
        assert meta.search_volume == 1000
        assert meta.ranking_position == 3


class TestIntelligenceRecord:
    def test_creation_with_defaults(self):
        record = IntelligenceRecord(
            url="https://example.com/page",
            competitor_domain="example.com",
        )
        assert record.url == "https://example.com/page"
        assert record.competitor_domain == "example.com"
        assert record.source == "seranking_competitor"
        assert record.collected_at  # auto-populated
        assert record.content_hash == ""  # empty content → no hash

    def test_content_hash_auto_computed(self):
        record = IntelligenceRecord(
            url="https://example.com/page",
            competitor_domain="example.com",
            content="Hello world content",
        )
        assert len(record.content_hash) == 16  # SHA-256 truncated to 16 chars

    def test_to_dict_roundtrip(self):
        record = IntelligenceRecord(
            url="https://example.com/page",
            competitor_domain="example.com",
            title="Test Page",
            content="Test content",
            page_type="product",
            seranking=SerankingMeta(
                keyword="test kw",
                cluster_id="kc-1",
                intent="commercial",
                search_volume=500,
                difficulty=30.0,
                ranking_position=5,
            ),
            headings=["H1", "H2"],
            description="A description",
            faq=[{"question": "Q?", "answer": "A."}],
            word_count=100,
        )
        d = record.to_dict()
        assert d["url"] == "https://example.com/page"
        assert d["seranking"]["keyword"] == "test kw"
        assert d["seranking"]["ranking_position"] == 5
        assert d["headings"] == ["H1", "H2"]

        # Roundtrip
        restored = IntelligenceRecord.from_dict(d)
        assert restored.url == record.url
        assert restored.seranking.keyword == "test kw"
        assert restored.seranking.ranking_position == 5
        assert restored.headings == ["H1", "H2"]
        assert restored.content_hash == record.content_hash

    def test_to_dify_text_includes_provenance(self):
        record = IntelligenceRecord(
            url="https://example.com/page",
            competitor_domain="example.com",
            title="My Page",
            content="Page content here",
            page_type="product",
            seranking=SerankingMeta(
                keyword="meta ads",
                cluster_id="kc-meta-1",
                intent="commercial",
                search_volume=10000,
                difficulty=65.0,
                ranking_position=2,
            ),
        )
        text = record.to_dify_text()
        assert "https://example.com/page" in text
        assert "example.com" in text
        assert "meta ads" in text
        assert "kc-meta-1" in text
        assert "commercial" in text
        assert "10000" in text
        assert "65.0" in text
        assert "2" in text
        assert "seranking_competitor" in text
        assert "Page content here" in text
