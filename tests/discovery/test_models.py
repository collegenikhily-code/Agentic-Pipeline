"""Tests for discovery data models."""

import pytest

from seo_aeo_geo_pipeline.discovery.models import (
    CompetitorPage,
    KeywordCluster,
    KeywordObservation,
    PageOpportunity,
)


class TestKeywordObservation:
    def test_default_values(self):
        obs = KeywordObservation(keyword="test keyword")
        assert obs.keyword == "test keyword"
        assert obs.search_volume == 0
        assert obs.difficulty == 0
        assert obs.cpc == 0.0
        assert obs.competition == 0.0
        assert obs.intent == ""
        assert obs.serp_features == []
        assert obs.ranking_domain == ""
        assert obs.ranking_url == ""
        assert obs.ranking_position is None
        assert obs.our_position is None
        assert obs.source == "se_ranking"

    def test_to_dict(self):
        obs = KeywordObservation(
            keyword="crm software",
            search_volume=320,
            difficulty=38,
            intent="commercial",
        )
        d = obs.to_dict()
        assert d["keyword"] == "crm software"
        assert d["search_volume"] == 320
        assert d["difficulty"] == 38
        assert d["intent"] == "commercial"

    def test_equality(self):
        a = KeywordObservation(keyword="kw1", search_volume=100)
        b = KeywordObservation(keyword="kw1", search_volume=100)
        assert a == b

    def test_inequality(self):
        a = KeywordObservation(keyword="kw1", search_volume=100)
        b = KeywordObservation(keyword="kw2", search_volume=100)
        assert a != b

    def test_to_dict_contains_all_fields(self):
        obs = KeywordObservation(keyword="test")
        d = obs.to_dict()
        expected_keys = {
            "keyword", "search_volume", "difficulty", "cpc", "competition",
            "intent", "serp_features", "ranking_domain", "ranking_url",
            "ranking_position", "our_position", "source",
        }
        assert expected_keys == set(d.keys())


class TestCompetitorPage:
    def test_default_values(self):
        page = CompetitorPage(domain="comp.com", url="https://comp.com/page")
        assert page.domain == "comp.com"
        assert page.url == "https://comp.com/page"
        assert page.keywords == []
        assert page.ranking_positions == {}
        assert page.avg_volume == 0.0
        assert page.avg_difficulty == 0.0

    def test_to_dict(self):
        page = CompetitorPage(
            domain="comp.com",
            url="https://comp.com/page",
            keywords=["kw1", "kw2"],
            avg_volume=150.0,
            avg_difficulty=35.0,
        )
        d = page.to_dict()
        assert d["domain"] == "comp.com"
        assert d["keywords"] == ["kw1", "kw2"]
        assert d["avg_volume"] == 150.0


class TestKeywordCluster:
    def test_default_values(self):
        kc = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="test",
            keywords=["test"],
        )
        assert kc.cluster_id == "kc-1"
        assert kc.primary_keyword == "test"
        assert kc.total_search_volume == 0
        assert kc.avg_difficulty == 0.0
        assert kc.competitor_pages == []
        assert kc.supporting_questions == []

    def test_to_dict(self):
        kc = KeywordCluster(
            cluster_id="kc-1",
            primary_keyword="test",
            keywords=["test", "test2"],
            total_search_volume=500,
            avg_difficulty=25.0,
        )
        d = kc.to_dict()
        assert d["cluster_id"] == "kc-1"
        assert d["total_search_volume"] == 500
        assert len(d["keywords"]) == 2


class TestPageOpportunity:
    def test_default_values(self):
        opp = PageOpportunity(
            opportunity_id="opp-1",
            primary_keyword="test kw",
            recommended_page_type="guide",
            recommended_slug="/test-kw",
            opportunity_reason="Test reason",
        )
        assert opp.opportunity_id == "opp-1"
        assert opp.search_volume == 0
        assert opp.difficulty == 0.0
        assert opp.secondary_keywords == []
        assert opp.competitor_pages == []
        assert opp.questions == []
        assert opp.serp_features == []

    def test_to_dict(self):
        opp = PageOpportunity(
            opportunity_id="opp-1",
            primary_keyword="best crm",
            secondary_keywords=["top crm", "crm comparison"],
            search_volume=300,
            difficulty=42.0,
            recommended_page_type="comparison-guide",
            recommended_slug="/best-crm",
            opportunity_reason="Good opportunity",
        )
        d = opp.to_dict()
        assert d["opportunity_id"] == "opp-1"
        assert d["primary_keyword"] == "best crm"
        assert len(d["secondary_keywords"]) == 2
        assert d["recommended_page_type"] == "comparison-guide"
