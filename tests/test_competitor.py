"""Unit tests for the competitor intelligence subsystem."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from seo_aeo_geo_pipeline.competitor.models import (
    CompetitorConfig,
    CompetitorEvidence,
    CompetitorResearchPack,
    CrawlConfig,
    CrawledPage,
)
from seo_aeo_geo_pipeline.competitor.config import load_competitor_config
from seo_aeo_geo_pipeline.competitor.crawler import CompetitorCrawler, _normalize_url
from seo_aeo_geo_pipeline.competitor.extractor import extract_content, _clean_text, _extract_faq
from seo_aeo_geo_pipeline.competitor.storage import CompetitorStore
from seo_aeo_geo_pipeline.competitor.classifier import classify_page, classify_all
from seo_aeo_geo_pipeline.competitor.retriever import retrieve_relevant, _tfidf_score, _tokenize
from seo_aeo_geo_pipeline.competitor.intel import CompetitorIntel


# ── Models ─────────────────────────────────────────────────────────────────────

class TestCrawlConfig:
    def test_defaults(self):
        config = CrawlConfig()
        assert config.enabled is False
        assert config.max_pages_per_domain == 10
        assert config.global_concurrency == 5
        assert config.cache_ttl_hours == 168

    def test_custom_values(self):
        config = CrawlConfig(enabled=True, max_pages_per_domain=20, cache_ttl_hours=24)
        assert config.enabled is True
        assert config.max_pages_per_domain == 20
        assert config.cache_ttl_hours == 24


class TestCompetitorConfig:
    def test_defaults(self):
        comp = CompetitorConfig(name="Test", domain="test.com")
        assert comp.enabled is True
        assert comp.max_pages == 10
        assert comp.priority == 0
        assert comp.seed_urls == []

    def test_custom_values(self):
        comp = CompetitorConfig(
            name="Test", domain="test.com",
            seed_urls=["https://test.com/product"],
            enabled=False,
            max_pages=5,
            priority=1,
        )
        assert comp.enabled is False
        assert comp.max_pages == 5
        assert comp.priority == 1


class TestCrawledPage:
    def test_creation(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/product",
        )
        assert page.competitor == "Test"
        assert page.domain == "test.com"
        assert page.url == "https://test.com/product"
        assert page.error is None
        assert page.word_count == 0

    def test_to_dict(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/product",
            title="Test Page",
            main_content="Test content",
        )
        d = page.__dict__
        assert d["title"] == "Test Page"
        assert d["main_content"] == "Test content"


class TestCompetitorEvidence:
    def test_creation(self):
        evidence = CompetitorEvidence(
            competitor="Test",
            url="https://test.com/product",
            page_type="product",
            relevant_content="Test content",
            relevant_headings=["Heading 1"],
            relevant_claims=["Claim 1"],
            relevance_score=0.5,
            crawled_at=datetime.now(timezone.utc).isoformat(),
        )
        assert evidence.competitor == "Test"
        assert evidence.relevance_score == 0.5


class TestCompetitorResearchPack:
    def test_empty_pack(self):
        pack = CompetitorResearchPack(opportunity_keyword="test keyword")
        assert pack.opportunity_keyword == "test keyword"
        assert pack.evidence == []
        assert pack.common_coverage == []
        assert pack.content_gaps == []


# ── Config ─────────────────────────────────────────────────────────────────────

class TestConfig:
    def test_load_from_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
crawl:
  enabled: true
  max_pages_per_domain: 5
  cache_ttl_hours: 48

competitors:
  - name: "Test Competitor"
    domain: "test.com"
    seed_urls:
      - "https://test.com/"
    enabled: true
    max_pages: 3
    priority: 5
""")
            config_path = f.name

        try:
            crawl_config, competitors = load_competitor_config(config_path)
            assert crawl_config.enabled is True
            assert crawl_config.max_pages_per_domain == 5
            assert len(competitors) == 1
            assert competitors[0].name == "Test Competitor"
            assert competitors[0].domain == "test.com"
        finally:
            Path(config_path).unlink()

    def test_load_defaults_when_missing(self):
        crawl_config, competitors = load_competitor_config("/nonexistent/path.yaml")
        assert crawl_config.enabled is False
        assert len(competitors) == 0


# ── Crawler Utilities ──────────────────────────────────────────────────────────

class TestCrawlerUtilities:
    def test_normalize_url(self):
        url = _normalize_url("https://example.com/path/")
        assert url == "https://example.com/path"
        assert url.endswith("/path") or url.endswith("example.com")

    def test_normalize_url_with_query(self):
        url = _normalize_url("https://example.com/path?q=test")
        assert "q=test" in url


# ── Extractor ──────────────────────────────────────────────────────────────────

class TestExtractor:
    def test_clean_text(self):
        assert _clean_text("  Hello   world  ") == "Hello world"
        assert _clean_text("Line1\nLine2") == "Line1 Line2"

    def test_extract_faq_from_json_ld(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {
            "@type": "FAQPage",
            "mainEntity": [{
                "@type": "Question",
                "name": "What is this?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "This is a test product."
                }
            }]
        }
        </script>
        </head><body></body></html>
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        faq = _extract_faq(soup)
        assert len(faq) == 1
        assert faq[0]["question"] == "What is this?"
        assert faq[0]["answer"] == "This is a test product."

    def test_extract_content(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/",
        )
        page.main_content = """
        <html>
        <head><title>Test Page</title></head>
        <body>
        <nav>Navigation</nav>
        <main>
            <h1>Main Heading</h1>
            <p>This is test content about automation.</p>
            <p>More content about features.</p>
        </main>
        <footer>Footer content</footer>
        </body>
        </html>
        """
        result = extract_content(page)
        assert result.title == "Test Page"
        assert result.word_count > 0
        assert result.content_hash is not None
        assert len(result.headings) > 0


# ── Storage ────────────────────────────────────────────────────────────────────

class TestStorage:
    def test_store_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir, cache_ttl_hours=24)

            page = CrawledPage(
                competitor="Test",
                domain="test.com",
                url="https://test.com/product",
                title="Product Page",
                main_content="Product content",
            )
            page.content_hash = "abc123"

            # Store
            store.put(page)

            # Retrieve
            retrieved = store.get("https://test.com/product", "test.com")
            assert retrieved is not None
            assert retrieved.title == "Product Page"
            assert retrieved.main_content == "Product content"

    def test_cache_hit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir, cache_ttl_hours=24)

            page = CrawledPage(
                competitor="Test",
                domain="test.com",
                url="https://test.com/",
                title="Test",
            )
            page.content_hash = "hash1"
            store.put(page)

            assert store.has("https://test.com/", "test.com") is True

    def test_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir)
            assert store.has("https://nonexistent.com/", "nonexistent.com") is False

    def test_list_pages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir)

            for i in range(3):
                page = CrawledPage(
                    competitor="Test",
                    domain="test.com",
                    url=f"https://test.com/page{i}",
                )
                page.content_hash = f"hash{i}"
                store.put(page)

            pages = store.list_pages("test.com")
            assert len(pages) == 3

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir)

            page = CrawledPage(
                competitor="Test",
                domain="test.com",
                url="https://test.com/",
            )
            page.content_hash = "hash1"
            store.put(page)

            stats = store.stats()
            assert stats["test.com"] == 1


# ── Classifier ─────────────────────────────────────────────────────────────────

class TestClassifier:
    def test_classify_pricing_page(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/pricing",
            title="Pricing Plans",
        )
        assert classify_page(page) == "pricing"

    def test_classify_faq_page(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/faq",
            title="FAQ",
        )
        assert classify_page(page) == "faq"

    def test_classify_homepage(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/",
            title="Home",
        )
        assert classify_page(page) == "product"

    def test_classify_by_title(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/other",
            title="Our Features",
        )
        assert classify_page(page) == "feature"

    def test_classify_all(self):
        pages = [
            CrawledPage(competitor="Test", domain="test.com", url="https://test.com/pricing", title="Pricing"),
            CrawledPage(competitor="Test", domain="test.com", url="https://test.com/faq", title="FAQ"),
            CrawledPage(competitor="Test", domain="test.com", url="https://test.com/", title="Home"),
        ]
        classified = classify_all(pages)
        assert classified[0].page_type == "pricing"
        assert classified[1].page_type == "faq"
        assert classified[2].page_type == "product"


# ── Retriever ──────────────────────────────────────────────────────────────────

class TestRetriever:
    def test_tokenize(self):
        tokens = _tokenize("Hello World Test")
        assert tokens == ["hello", "world", "test"]

    def test_tfidf_score(self):
        query = ["google", "ads", "automation"]
        doc = ["google", "ads", "automation", "tool", "platform"]
        score = _tfidf_score(query, doc)
        assert score > 0

    def test_retrieve_relevant(self):
        pages = [
            CrawledPage(
                competitor="Test1",
                domain="test1.com",
                url="https://test1.com/product",
                title="Google Ads Automation Tool",
                main_content="Automate your Google Ads campaigns with AI. Features include automated bidding and ad scheduling.",
            ),
            CrawledPage(
                competitor="Test2",
                domain="test2.com",
                url="https://test2.com/product",
                title="Facebook Ads Management",
                main_content="Manage your Facebook ads with ease. No Google Ads support.",
            ),
        ]

        evidence = retrieve_relevant(pages, "google ads automation", top_k=2)
        assert len(evidence) > 0
        # First result should be more relevant to "google ads automation"
        assert evidence[0].competitor == "Test1"
        assert evidence[0].relevance_score > 0

    def test_empty_pages(self):
        evidence = retrieve_relevant([], "test", top_k=5)
        assert evidence == []


# ── Intel (Integration) ───────────────────────────────────────────────────────

class TestCompetitorIntel:
    def test_initialization(self):
        config = CrawlConfig(enabled=True)
        competitors = [
            CompetitorConfig(name="Test", domain="test.com", seed_urls=["https://test.com/"]),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir)
            intel = CompetitorIntel(config, competitors, store)
            assert "test.com" in intel.competitors
            assert intel.competitors["test.com"].name == "Test"

    def test_from_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
crawl:
  enabled: false
  max_pages_per_domain: 3

competitors:
  - name: "Test"
    domain: "test.com"
    seed_urls: ["https://test.com/"]
    enabled: true
""")
            config_path = f.name

        try:
            intel = CompetitorIntel.from_config(config_path)
            assert "test.com" in intel.competitors
        finally:
            Path(config_path).unlink()

    def test_build_research_pack_empty(self):
        config = CrawlConfig(enabled=True)
        competitors = [
            CompetitorConfig(name="Test", domain="test.com", seed_urls=["https://test.com/"]),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir)
            intel = CompetitorIntel(config, competitors, store)
            pack = intel.build_research_pack("test keyword")
            assert pack.evidence == []

    def test_build_research_pack_with_pages(self):
        config = CrawlConfig(enabled=True)
        competitors = [
            CompetitorConfig(name="Test", domain="test.com", seed_urls=["https://test.com/"]),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir)
            intel = CompetitorIntel(config, competitors, store)

            # Manually populate cache
            page = CrawledPage(
                competitor="Test",
                domain="test.com",
                url="https://test.com/product",
                title="Google Ads Automation Platform",
                main_content="Automate your Google Ads campaigns with AI-powered tools.",
                page_type="product",
            )
            page.content_hash = "test123"
            store.put(page)

            pack = intel.build_research_pack("google ads automation")
            assert len(pack.evidence) > 0
            assert pack.evidence[0].competitor == "Test"


# ── Edge Cases ─────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_html_extraction(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/",
        )
        page.main_content = ""
        result = extract_content(page)
        assert result.main_content == ""

    def test_malformed_html(self):
        page = CrawledPage(
            competitor="Test",
            domain="test.com",
            url="https://test.com/",
        )
        page.main_content = "<html><body><h1>Test</h1><p>Content</body></html>"
        result = extract_content(page)
        assert result.title == ""

    def test_storage_ttl_expiry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CompetitorStore(tmpdir, cache_ttl_hours=0)  # Immediate expiry

            page = CrawledPage(
                competitor="Test",
                domain="test.com",
                url="https://test.com/",
            )
            page.content_hash = "hash1"
            store.put(page)

            # Should be expired immediately
            import time
            time.sleep(0.01)
            assert store.has("https://test.com/", "test.com") is False
