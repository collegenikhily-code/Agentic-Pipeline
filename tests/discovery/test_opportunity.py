"""Tests for opportunity generation."""

from seo_aeo_geo_pipeline.discovery.models import KeywordCluster, KeywordObservation
from seo_aeo_geo_pipeline.discovery.opportunity import (
    _detect_page_type,
    _slugify,
    cluster_to_opportunity,
    clusters_to_opportunities,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("CRM Software") == "crm-software"

    def test_special_chars(self):
        assert _slugify("What's the best CRM?") == "whats-the-best-crm"

    def test_multiple_spaces(self):
        assert _slugify("hello   world") == "hello-world"


class TestDetectPageType:
    def test_comparison_signals(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="best crm for textile manufacturers",
            keywords=["best crm for textile manufacturers", "top crm comparison"],
            dominant_intent="commercial",
        )
        assert _detect_page_type(cluster, []) == "comparison-guide"

    def test_vs_signal(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="hubspot vs salesforce",
            keywords=["hubspot vs salesforce"],
            dominant_intent="commercial",
        )
        assert _detect_page_type(cluster, []) == "comparison-guide"

    def test_alternative_signal(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="hubspot alternatives",
            keywords=["hubspot alternatives", "like hubspot"],
            dominant_intent="commercial",
        )
        assert _detect_page_type(cluster, []) == "alternatives-page"

    def test_how_to_signal(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="how to use crm",
            keywords=["how to use crm", "crm guide"],
            dominant_intent="informational",
        )
        assert _detect_page_type(cluster, []) == "guide"

    def test_commercial_default(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="buy crm software",
            keywords=["buy crm software"],
            dominant_intent="commercial",
        )
        assert _detect_page_type(cluster, []) == "comparison-guide"

    def test_transactional_default(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="crm pricing",
            keywords=["crm pricing"],
            dominant_intent="transactional",
        )
        assert _detect_page_type(cluster, []) == "product-page"

    def test_informational_default(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="what is crm",
            keywords=["what is crm"],
            dominant_intent="informational",
        )
        assert _detect_page_type(cluster, []) == "guide"

    def test_unknown_intent(self):
        cluster = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="random keyword",
            keywords=["random keyword"],
            dominant_intent="unknown",
        )
        assert _detect_page_type(cluster, []) == "reference-page"


class TestClusterToOpportunity:
    def test_basic_conversion(self):
        cluster = KeywordCluster(
            cluster_id="kc-textile-crm-abc12345",
            primary_keyword="crm for textile manufacturers",
            keywords=[
                "crm for textile manufacturers",
                "best textile crm",
                "textile manufacturing crm software",
            ],
            dominant_intent="commercial",
            total_search_volume=600,
            avg_difficulty=38.0,
            competitor_pages=["https://a.com/textile-crm"],
            supporting_questions=["what is textile crm"],
        )
        opp = cluster_to_opportunity(cluster)
        assert opp.primary_keyword == "crm for textile manufacturers"
        assert len(opp.secondary_keywords) == 2
        assert opp.search_volume == 600
        assert opp.difficulty == 38.0
        assert opp.intent == "commercial"
        assert "comparison-guide" in opp.recommended_page_type
        assert opp.recommended_slug == "/crm-for-textile-manufacturers"
        assert "600" in opp.opportunity_reason
        assert len(opp.opportunity_id) > 0

    def test_opportunity_has_questions(self):
        cluster = KeywordCluster(
            cluster_id="kc-test",
            primary_keyword="best crm",
            keywords=["best crm"],
            dominant_intent="commercial",
            supporting_questions=["what is crm", "how to choose crm"],
        )
        opp = cluster_to_opportunity(cluster)
        assert opp.questions == ["what is crm", "how to choose crm"]

    def test_opportunity_has_serp_features(self):
        cluster = KeywordCluster(
            cluster_id="kc-test",
            primary_keyword="test kw",
            keywords=["test kw"],
            serp_features=["featured_snippets", "people_also_ask"],
        )
        opp = cluster_to_opportunity(cluster)
        assert "featured_snippets" in opp.serp_features

    def test_opportunity_slug_is_unique(self):
        c1 = KeywordCluster(cluster_id="kc-a", primary_keyword="keyword one", keywords=["keyword one"])
        c2 = KeywordCluster(cluster_id="kc-b", primary_keyword="keyword two", keywords=["keyword two"])
        o1 = cluster_to_opportunity(c1)
        o2 = cluster_to_opportunity(c2)
        assert o1.opportunity_id != o2.opportunity_id
        assert o1.recommended_slug != o2.recommended_slug


class TestClustersToOpportunities:
    def test_sorted_by_volume(self):
        c1 = KeywordCluster(
            cluster_id="kc-1", primary_keyword="small", keywords=["small"],
            total_search_volume=10,
        )
        c2 = KeywordCluster(
            cluster_id="kc-2", primary_keyword="big", keywords=["big"],
            total_search_volume=500,
        )
        opps = clusters_to_opportunities([c1, c2])
        assert opps[0].primary_keyword == "big"
        assert opps[1].primary_keyword == "small"

    def test_empty_clusters(self):
        opps = clusters_to_opportunities([])
        assert opps == []
