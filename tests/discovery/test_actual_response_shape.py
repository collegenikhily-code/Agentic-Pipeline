"""Regression tests using the ACTUAL SE Ranking /v1/domain/keywords response shape.

The real API returns a list of dicts, NOT a dict with a "keywords" key.
These tests use the exact field names and types observed from live API calls.
"""

import pytest

from seo_aeo_geo_pipeline.discovery.normalizer import normalize_keywords_response
from seo_aeo_geo_pipeline.discovery.models import KeywordObservation


# The actual response shape observed from SE Ranking /v1/domain/keywords
ACTUAL_KEYWORDS_RESPONSE = [
    {
        "block_type": None,
        "block_position": 28,
        "keyword": "meta moment maker",
        "position": 28,
        "prev_pos": 28,
        "volume": 390,
        "cpc": 13.21,
        "competition": 0.1,
        "url": "https://www.adspirer.com/blog",
        "difficulty": 7,
        "total_sites": None,
        "traffic": 3,
        "traffic_percent": 17.65,
        "price": 39.63,
        "serp_features": [
            "video",
            "people_also_ask",
            "sge",
            "related_searches",
        ],
        "intents": [
            "I",
        ],
    },
    {
        "block_type": None,
        "block_position": 14,
        "keyword": "ads automation",
        "position": 14,
        "prev_pos": 14,
        "volume": 140,
        "cpc": 8.03,
        "competition": 0.14,
        "url": "https://www.adspirer.com/blog/google-ads-automation",
        "difficulty": 6,
        "total_sites": None,
        "traffic": 2,
        "traffic_percent": 11.76,
        "price": 16.06,
        "serp_features": [
            "reviews",
            "video",
            "gmb",
            "related_searches",
        ],
        "intents": [
            "L",
            "C",
        ],
    },
    {
        "block_type": None,
        "block_position": 6,
        "keyword": "adspire",
        "position": 6,
        "prev_pos": 6,
        "volume": 110,
        "cpc": 8.25,
        "competition": 0.27,
        "url": "https://www.adspirer.com/",
        "difficulty": 9,
        "total_sites": None,
        "traffic": 1,
        "traffic_percent": 5.88,
        "price": 8.25,
        "serp_features": [
            "reviews",
            "video",
            "people_also_ask",
            "images",
            "gmb",
            "related_searches",
        ],
        "intents": [
            "L",
            "C",
        ],
    },
    {
        "block_type": "sge",
        "block_position": 1,
        "keyword": "google ads automation",
        "position": 1,
        "prev_pos": 1,
        "volume": 70,
        "cpc": 7.01,
        "competition": 0.31,
        "url": "https://www.adspirer.com/blog/google-ads-automation",
        "difficulty": 25,
        "total_sites": None,
        "traffic": 1,
        "traffic_percent": 5.88,
        "price": 7.01,
        "serp_features": [
            "reviews",
            "video",
            "sge",
            "related_searches",
        ],
        "intents": [
            "I",
        ],
    },
]


class TestActualSERankingResponseShape:
    """Regression: /v1/domain/keywords returns a list, not a dict."""

    def test_direct_list_response_normalizes(self):
        """The actual API response is a list. Normalizer must handle this."""
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        assert len(result) == 4

    def test_all_keywords_extracted(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        keywords = {o.keyword for o in result}
        assert keywords == {
            "meta moment maker",
            "ads automation",
            "adspire",
            "google ads automation",
        }

    def test_search_volume_preserved(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        assert by_kw["meta moment maker"].search_volume == 390
        assert by_kw["ads automation"].search_volume == 140
        assert by_kw["adspire"].search_volume == 110
        assert by_kw["google ads automation"].search_volume == 70

    def test_difficulty_preserved(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        assert by_kw["meta moment maker"].difficulty == 7
        assert by_kw["google ads automation"].difficulty == 25

    def test_cpc_preserved(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        assert by_kw["meta moment maker"].cpc == 13.21
        assert by_kw["ads automation"].cpc == 8.03

    def test_competition_preserved(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        assert by_kw["meta moment maker"].competition == 0.1
        assert by_kw["google ads automation"].competition == 0.31

    def test_ranking_position_preserved(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        assert by_kw["meta moment maker"].ranking_position == 28
        assert by_kw["google ads automation"].ranking_position == 1

    def test_ranking_url_preserved(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        assert by_kw["meta moment maker"].ranking_url == "https://www.adspirer.com/blog"
        assert by_kw["adspire"].ranking_url == "https://www.adspirer.com/"

    def test_intent_from_array(self):
        """intents field is an array of single-char codes."""
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        # "meta moment maker" has intents: ["I"] → informational
        assert by_kw["meta moment maker"].intent == "informational"
        # "ads automation" has intents: ["L", "C"] → local (first)
        assert by_kw["ads automation"].intent == "local"

    def test_serp_features_preserved(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        by_kw = {o.keyword: o for o in result}
        assert "video" in by_kw["meta moment maker"].serp_features
        assert "sge" in by_kw["meta moment maker"].serp_features
        assert "people_also_ask" in by_kw["meta moment maker"].serp_features
        assert "reviews" in by_kw["google ads automation"].serp_features

    def test_source_domain_set(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        for obs in result:
            assert obs.ranking_domain == "adspirer.com"

    def test_source_field_set(self):
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        for obs in result:
            assert obs.source == "se_ranking"

    def test_unknown_fields_ignored(self):
        """Fields like block_type, prev_pos, total_sites, traffic, price
        are present in the API response but not in our model.
        Normalizer should ignore them without crashing."""
        result = normalize_keywords_response(
            ACTUAL_KEYWORDS_RESPONSE, source_domain="adspirer.com"
        )
        assert len(result) == 4
        # None of the extra fields should appear in the model
        for obs in result:
            d = obs.to_dict()
            assert "block_type" not in d
            assert "prev_pos" not in d
            assert "total_sites" not in d
            assert "traffic" not in d
            assert "traffic_percent" not in d
            assert "price" not in d

    def test_empty_list_response(self):
        result = normalize_keywords_response([], source_domain="test.com")
        assert result == []

    def test_dict_response_still_works(self):
        """Ensure the dict response shape still works (backward compat)."""
        dict_response = {
            "keywords": [
                {"keyword": "test kw", "volume": 100, "position": 5},
            ]
        }
        result = normalize_keywords_response(dict_response)
        assert len(result) == 1
        assert result[0].keyword == "test kw"

    def test_malformed_record_in_list_skipped(self):
        """A bad record in the list should not crash the entire normalization."""
        response_with_bad = [
            {"keyword": "good kw", "volume": 100, "position": 1},
            "not a dict",
            {"keyword": "", "volume": 50},
            {"keyword": "also good", "volume": 200},
        ]
        result = normalize_keywords_response(response_with_bad)
        assert len(result) == 2
        assert result[0].keyword == "good kw"
        assert result[1].keyword == "also good"
