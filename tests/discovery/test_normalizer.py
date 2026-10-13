"""Tests for keyword normalization."""

import pytest

from seo_aeo_geo_pipeline.discovery.normalizer import (
    build_competitor_pages,
    build_keyword_page_map,
    normalize_keyword_record,
    normalize_keywords_response,
    normalize_overlap_response,
    normalize_question_keywords,
    normalize_related_keywords,
)
from seo_aeo_geo_pipeline.discovery.models import KeywordObservation


class TestNormalizeKeywordRecord:
    def test_normal_record(self):
        record = {
            "keyword": "crm for textile manufacturers",
            "volume": 320,
            "difficulty": 38,
            "cpc": 4.2,
            "competition": 0.41,
            "intents": ["C"],
            "serp_features": ["featured_snippets"],
            "base_domain": "competitor.com",
            "url": "https://competitor.com/textile-crm",
            "position": 4,
        }
        obs = normalize_keyword_record(record, source_domain="test.com")
        assert obs is not None
        assert obs.keyword == "crm for textile manufacturers"
        assert obs.search_volume == 320
        assert obs.difficulty == 38
        assert obs.cpc == 4.2
        assert obs.competition == 0.41
        assert obs.intent == "commercial"
        assert obs.serp_features == ["featured_snippets"]
        assert obs.ranking_domain == "competitor.com"
        assert obs.ranking_url == "https://competitor.com/textile-crm"
        assert obs.ranking_position == 4

    def test_missing_keyword_returns_none(self):
        record = {"volume": 100}
        obs = normalize_keyword_record(record)
        assert obs is None

    def test_empty_keyword_returns_none(self):
        record = {"keyword": "", "volume": 100}
        obs = normalize_keyword_record(record)
        assert obs is None

    def test_missing_url(self):
        record = {"keyword": "test", "volume": 100}
        obs = normalize_keyword_record(record)
        assert obs is not None
        assert obs.ranking_url == ""

    def test_missing_intent(self):
        record = {"keyword": "test", "volume": 100}
        obs = normalize_keyword_record(record)
        assert obs is not None
        assert obs.intent == ""

    def test_missing_metrics(self):
        record = {"keyword": "test"}
        obs = normalize_keyword_record(record)
        assert obs is not None
        assert obs.search_volume == 0
        assert obs.difficulty == 0
        assert obs.cpc == 0.0

    def test_malformed_record_returns_none(self):
        record = "not a dict"
        obs = normalize_keyword_record(record)
        assert obs is None

    def test_intent_array_conversion(self):
        assert normalize_keyword_record({"keyword": "k", "intents": ["I"]}).intent == "informational"
        assert normalize_keyword_record({"keyword": "k", "intents": ["C"]}).intent == "commercial"
        assert normalize_keyword_record({"keyword": "k", "intents": ["T"]}).intent == "transactional"
        assert normalize_keyword_record({"keyword": "k", "intents": ["L"]}).intent == "local"
        assert normalize_keyword_record({"keyword": "k", "intents": ["N"]}).intent == "navigational"

    def test_intent_string_conversion(self):
        assert normalize_keyword_record({"keyword": "k", "intents": "I"}).intent == "informational"
        assert normalize_keyword_record({"keyword": "k", "intents": "C"}).intent == "commercial"

    def test_source_field(self):
        obs = normalize_keyword_record(
            {"keyword": "test"}, source="custom_source"
        )
        assert obs.source == "custom_source"


class TestNormalizeKeywordsResponse:
    def test_normal_response(self):
        response = {
            "keywords": [
                {"keyword": "kw1", "volume": 100, "position": 1},
                {"keyword": "kw2", "volume": 200, "position": 5},
            ]
        }
        result = normalize_keywords_response(response, source_domain="test.com")
        assert len(result) == 2
        assert result[0].keyword == "kw1"

    def test_empty_response(self):
        result = normalize_keywords_response({"keywords": []})
        assert len(result) == 0

    def test_skips_malformed_records(self):
        response = {
            "keywords": [
                {"keyword": "good", "volume": 100},
                "bad_record",
                {"keyword": "", "volume": 50},
                {"keyword": "also_good", "volume": 200},
            ]
        }
        result = normalize_keywords_response(response)
        assert len(result) == 2

    def test_dict_wrapped_keywords(self):
        response = {"result": {"keywords": [{"keyword": "test"}]}}
        result = normalize_keywords_response(response)
        assert len(result) == 1


class TestNormalizeOverlapResponse:
    def test_normal_overlap(self):
        response = {
            "only_domain1": [{"keyword": "our-only", "volume": 100}],
            "only_domain2": [{"keyword": "comp-only", "volume": 200}],
            "common": [{"keyword": "shared", "volume": 150}],
        }
        result = normalize_overlap_response(response)
        assert len(result["only_our"]) == 1
        assert len(result["only_competitor"]) == 1
        assert len(result["common"]) == 1
        assert result["only_our"][0].keyword == "our-only"
        assert result["only_competitor"][0].keyword == "comp-only"

    def test_empty_overlap(self):
        result = normalize_overlap_response({})
        assert len(result["only_our"]) == 0
        assert len(result["only_competitor"]) == 0
        assert len(result["common"]) == 0


class TestNormalizeRelatedAndQuestions:
    def test_related_keywords(self):
        response = {
            "total": 2,
            "keywords": [
                {"keyword": "related kw1", "volume": 50},
                {"keyword": "related kw2", "volume": 75},
            ],
        }
        result = normalize_related_keywords(response)
        assert len(result) == 2

    def test_question_keywords(self):
        response = {
            "total": 2,
            "keywords": [
                {"keyword": "what is crm", "volume": 300},
                {"keyword": "how to use crm", "volume": 200},
            ],
        }
        result = normalize_question_keywords(response)
        assert len(result) == 2
        assert result[0].keyword == "what is crm"


class TestBuildKeywordPageMap:
    def test_basic_mapping(self):
        obs = [
            KeywordObservation(keyword="kw1", ranking_url="https://a.com/page1"),
            KeywordObservation(keyword="kw2", ranking_url="https://a.com/page1"),
            KeywordObservation(keyword="kw3", ranking_url="https://a.com/page2"),
        ]
        page_map = build_keyword_page_map(obs)
        assert "https://a.com/page1" in page_map
        assert len(page_map["https://a.com/page1"]) == 2
        assert len(page_map["https://a.com/page2"]) == 1

    def test_empty_url_skipped(self):
        obs = [KeywordObservation(keyword="kw1", ranking_url="")]
        page_map = build_keyword_page_map(obs)
        assert len(page_map) == 0


class TestBuildCompetitorPages:
    def test_groups_by_url(self):
        obs = [
            KeywordObservation(
                keyword="kw1",
                search_volume=100,
                difficulty=30,
                ranking_domain="comp.com",
                ranking_url="https://comp.com/page1",
                ranking_position=3,
            ),
            KeywordObservation(
                keyword="kw2",
                search_volume=200,
                difficulty=40,
                ranking_domain="comp.com",
                ranking_url="https://comp.com/page1",
                ranking_position=7,
            ),
        ]
        pages = build_competitor_pages(obs)
        assert len(pages) == 1
        assert pages[0].url == "https://comp.com/page1"
        assert len(pages[0].keywords) == 2
        assert pages[0].avg_volume == 150.0
        assert pages[0].avg_difficulty == 35.0
