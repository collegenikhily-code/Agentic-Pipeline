"""Tests for keyword clustering."""

from seo_aeo_geo_pipeline.discovery.clustering import cluster_keywords
from seo_aeo_geo_pipeline.discovery.models import KeywordObservation


class TestClusterKeywords:
    def test_empty_observations(self):
        result = cluster_keywords([])
        assert result == []

    def test_single_keyword(self):
        obs = [KeywordObservation(keyword="crm software", search_volume=100, intent="commercial")]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 1
        assert clusters[0].primary_keyword == "crm software"
        assert clusters[0].keywords == ["crm software"]
        assert clusters[0].dominant_intent == "commercial"

    def test_grouped_by_url(self):
        obs = [
            KeywordObservation(
                keyword="crm for textile",
                search_volume=100,
                ranking_url="https://a.com/crm",
            ),
            KeywordObservation(
                keyword="textile crm",
                search_volume=80,
                ranking_url="https://a.com/crm",
            ),
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 1
        assert len(clusters[0].keywords) == 2

    def test_separate_by_intent(self):
        obs = [
            KeywordObservation(keyword="best crm", search_volume=100, intent="commercial"),
            KeywordObservation(keyword="what is crm", search_volume=200, intent="informational"),
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 2
        intents = {c.dominant_intent for c in clusters}
        assert intents == {"commercial", "informational"}

    def test_grouped_by_text_similarity(self):
        obs = [
            KeywordObservation(
                keyword="crm for manufacturers",
                search_volume=100,
                intent="commercial",
            ),
            KeywordObservation(
                keyword="best crm for manufacturers",
                search_volume=80,
                intent="commercial",
            ),
        ]
        clusters = cluster_keywords(obs, min_overlap_ratio=0.3)
        assert len(clusters) == 1
        assert len(clusters[0].keywords) == 2

    def test_sorted_by_total_volume(self):
        obs = [
            KeywordObservation(keyword="small", search_volume=10, intent="informational"),
            KeywordObservation(keyword="big topic", search_volume=500, intent="informational"),
            KeywordObservation(keyword="medium topic", search_volume=200, intent="informational"),
        ]
        clusters = cluster_keywords(obs)
        volumes = [c.total_search_volume for c in clusters]
        assert volumes == sorted(volumes, reverse=True)

    def test_cluster_has_serp_features(self):
        obs = [
            KeywordObservation(
                keyword="test kw",
                serp_features=["featured_snippets", "people_also_ask"],
            )
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 1
        assert "featured_snippets" in clusters[0].serp_features
        assert "people_also_ask" in clusters[0].serp_features

    def test_competitor_pages_populated(self):
        obs = [
            KeywordObservation(
                keyword="kw1",
                ranking_url="https://a.com/page1",
                ranking_domain="a.com",
            ),
            KeywordObservation(
                keyword="kw2",
                ranking_url="https://a.com/page2",
                ranking_domain="a.com",
            ),
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 2
        assert len(clusters[0].competitor_pages) == 1
        assert len(clusters[1].competitor_pages) == 1

    def test_keywords_deduplicated(self):
        obs = [
            KeywordObservation(keyword="crm", search_volume=100),
            KeywordObservation(keyword="crm", search_volume=100),
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 1
        assert len(clusters[0].keywords) == 1

    def test_unknown_intent_grouped_together(self):
        obs = [
            KeywordObservation(keyword="unknown kw1", search_volume=100),
            KeywordObservation(keyword="unknown kw2", search_volume=50),
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 2
        assert all(c.dominant_intent == "unknown" for c in clusters)
