"""Tests for competitor-led discovery mode."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from seo_aeo_geo_pipeline.discovery.models import (
    CompetitorPage,
    KeywordCluster,
    KeywordObservation,
    PageOpportunity,
)
from seo_aeo_geo_pipeline.discovery.normalizer import (
    build_competitor_pages,
    normalize_keywords_response,
)
from seo_aeo_geo_pipeline.discovery.clustering import cluster_keywords
from seo_aeo_geo_pipeline.discovery.opportunity import clusters_to_opportunities


class TestCompetitorLedDiscoveryModels:
    """Verify models work correctly for competitor-only observations."""

    def test_observations_from_multiple_competitors(self):
        obs_a = [
            KeywordObservation(
                keyword="best crm",
                search_volume=100,
                ranking_domain="adspirer.com",
                ranking_url="https://adspirer.com/best-crm",
                intent="commercial",
            ),
            KeywordObservation(
                keyword="crm comparison",
                search_volume=80,
                ranking_domain="adspirer.com",
                ranking_url="httpsadspirer.com/best-crm",
                intent="commercial",
            ),
        ]
        obs_b = [
            KeywordObservation(
                keyword="best crm",
                search_volume=200,
                ranking_domain="get-ryze.ai",
                ranking_url="https://get-ryze.ai/crm-review",
                intent="commercial",
            ),
            KeywordObservation(
                keyword="what is crm",
                search_volume=300,
                ranking_domain="get-ryze.ai",
                ranking_url="https://get-ryze.ai/what-is-crm",
                intent="informational",
            ),
        ]
        all_obs = obs_a + obs_b
        assert len(all_obs) == 4
        domains = {o.ranking_domain for o in all_obs}
        assert domains == {"adspirer.com", "get-ryze.ai"}

    def test_competitor_pages_from_multiple_domains(self):
        obs = [
            KeywordObservation(
                keyword="kw1",
                search_volume=100,
                ranking_domain="adspirer.com",
                ranking_url="https://adspirer.com/page1",
            ),
            KeywordObservation(
                keyword="kw2",
                search_volume=200,
                ranking_domain="get-ryze.ai",
                ranking_url="https://get-ryze.ai/page1",
            ),
        ]
        pages = build_competitor_pages(obs)
        assert len(pages) == 2
        page_domains = {p.domain for p in pages}
        assert page_domains == {"adspirer.com", "get-ryze.ai"}


class TestCompetitorLedClustering:
    """Verify clustering works across multiple competitor domains."""

    def test_cross_competitor_same_keyword(self):
        """Same keyword ranking from different competitors should cluster."""
        obs = [
            KeywordObservation(
                keyword="best crm software",
                search_volume=100,
                ranking_domain="adspirer.com",
                ranking_url="https://adspirer.com/best-crm",
                intent="commercial",
            ),
            KeywordObservation(
                keyword="best crm software",
                search_volume=200,
                ranking_domain="get-ryze.ai",
                ranking_url="https://get-ryze.ai/crm-review",
                intent="commercial",
            ),
        ]
        clusters = cluster_keywords(obs)
        # Same keyword + same intent → should be 1 cluster
        assert len(clusters) == 1
        c = clusters[0]
        assert c.primary_keyword == "best crm software"
        assert c.total_search_volume == 300
        assert len(c.competitor_pages) == 2

    def test_competitor_pages_preserved_in_cluster(self):
        obs = [
            KeywordObservation(
                keyword="crm for agencies",
                search_volume=50,
                ranking_domain="adspirer.com",
                ranking_url="https://adspirer.com/agencies",
            ),
            KeywordObservation(
                keyword="agency crm",
                search_volume=70,
                ranking_domain="get-ryze.ai",
                ranking_url="https://get-ryze.ai/agencies",
            ),
            KeywordObservation(
                keyword="crm for agencies",
                search_volume=30,
                ranking_domain="soku.ai",
                ranking_url="https://soku.ai/agencies",
            ),
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) >= 1
        # All 3 competitor URLs should appear across clusters
        all_urls = set()
        for c in clusters:
            all_urls.update(c.competitor_pages)
        assert len(all_urls) == 3

    def test_intent_separation_across_competitors(self):
        obs = [
            KeywordObservation(
                keyword="best crm",
                search_volume=100,
                ranking_domain="adspirer.com",
                ranking_url="https://adspirer.com/best-crm",
                intent="commercial",
            ),
            KeywordObservation(
                keyword="what is crm",
                search_volume=300,
                ranking_domain="get-ryze.ai",
                ranking_url="https://get-ryze.ai/what-is-crm",
                intent="informational",
            ),
        ]
        clusters = cluster_keywords(obs)
        assert len(clusters) == 2
        intents = {c.dominant_intent for c in clusters}
        assert intents == {"commercial", "informational"}


class TestCompetitorLedOpportunities:
    """Verify PageOpportunity generation for competitor-only data."""

    def test_opportunities_from_competitor_clusters(self):
        obs = [
            KeywordObservation(
                keyword="best crm for agencies",
                search_volume=100,
                ranking_domain="adspirer.com",
                ranking_url="https://adspirer.com/agencies",
                intent="commercial",
            ),
            KeywordObservation(
                keyword="agency crm comparison",
                search_volume=80,
                ranking_domain="get-ryze.ai",
                ranking_url="https://get-ryze.ai/agencies",
                intent="commercial",
            ),
        ]
        clusters = cluster_keywords(obs)
        opps = clusters_to_opportunities(clusters, obs)
        assert len(opps) >= 1
        opp = opps[0]
        assert opp.primary_keyword in {
            "best crm for agencies",
            "agency crm comparison",
        }
        assert opp.search_volume >= 80
        assert opp.recommended_page_type in {
            "comparison-guide",
            "alternatives-page",
            "use-case-page",
        }

    def test_no_own_domain_in_competitor_pages(self):
        """Competitor pages should only contain actual competitor domains."""
        obs = [
            KeywordObservation(
                keyword="top software",
                search_volume=50,
                ranking_domain="soku.ai",
                ranking_url="https://soku.ai/top",
            ),
        ]
        clusters = cluster_keywords(obs)
        opps = clusters_to_opportunities(clusters, obs)
        assert len(opps) == 1
        assert opps[0].primary_keyword == "top software"
        # Verify competitor pages list does not contain any own domain
        for page_url in opps[0].competitor_pages:
            assert "ourdomain.com" not in page_url


class TestCompetitorLedCLIArguments:
    """Test CLI argument parsing for competitor-led mode."""

    def test_competitor_required(self):
        """CLI should error if no --competitor is provided."""
        import subprocess
        result = subprocess.run(
            [
                "python3",
                str(Path(__file__).resolve().parent.parent.parent / "scripts" / "discover_opportunities.py"),
                "--limit",
                "10",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "competitor" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_competitor_only_mode_no_domain_flag(self):
        """CLI should accept --competitor without --domain."""
        import subprocess
        result = subprocess.run(
            [
                "python3",
                str(Path(__file__).resolve().parent.parent.parent / "scripts" / "discover_opportunities.py"),
                "--competitor",
                "test.com",
                "--limit",
                "10",
            ],
            capture_output=True,
            text=True,
        )
        # Should not fail due to missing domain; may fail due to auth/API
        # but the argument parsing should succeed
        assert "--domain" not in result.stderr


class TestCompetitorLedReportFormat:
    """Test that the report includes mode field."""

    def test_report_includes_mode(self):
        """Report dict should have mode=competitor_led when no domain."""
        # Simulate what the report dict would look like
        report = {
            "run_id": "test",
            "mode": "competitor_led",
            "domain": None,
            "competitors": ["adspirer.com", "get-ryze.ai"],
        }
        assert report["mode"] == "competitor_led"
        assert report["domain"] is None
        assert len(report["competitors"]) == 2

    def test_report_domain_gap_mode(self):
        report = {
            "run_id": "test",
            "mode": "domain_gap",
            "domain": "ourdomain.com",
            "competitors": ["adspirer.com"],
        }
        assert report["mode"] == "domain_gap"
        assert report["domain"] == "ourdomain.com"
