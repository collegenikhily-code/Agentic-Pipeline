"""Tests for Technical SEO gate."""

import pytest

from seo_aeo_geo_pipeline.gates.technical_seo import evaluate_technical_seo


VALID_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Test Page Title</title>
<meta name="description" content="Test meta description here.">
<link rel="canonical" href="https://example.com/test-page">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}</script>
</head>
<body>
<h1>Main Heading</h1>
<p>This is substantial content with many words to ensure it passes the minimum word count threshold for the content substance check which requires at least 80 words in the rendered body text of the page.</p>
<p>Additional paragraph with more words to increase the total word count well above the minimum threshold of eighty words required by the technical SEO validation gate for content substance.</p>
<p>Yet another paragraph containing even more text content so that the automated word counting logic will count enough words to satisfy the requirement for substantive page content.</p>
<a href="/internal-link">Internal Link</a>
<a href="https://example.com/another-page">Another Internal Link</a>
</body>
</html>"""


class TestTechnicalSEO:
    def test_pass_all_checks(self):
        result = evaluate_technical_seo(VALID_HTML)
        assert result["decision"] == "PASS"
        assert result["blocked"] is False
        assert len(result["warnings"]) == 0
        for check in result["checks"].values():
            assert check["passed"] is True

    def test_missing_canonical_advisory(self):
        html = VALID_HTML.replace('<link rel="canonical" href="https://example.com/test-page">', "")
        result = evaluate_technical_seo(html)
        # Advisory-only warning: decision should be PASS
        assert result["decision"] == "PASS"
        assert result["blocked"] is False
        assert result["checks"]["canonical"]["passed"] is False
        assert result["checks"]["canonical"]["severity"] == "advisory"
        assert "canonical" in str(result["warnings"]).lower()

    def test_missing_title_blocking(self):
        html = VALID_HTML.replace("<title>Test Page Title</title>", "<title></title>")
        result = evaluate_technical_seo(html)
        assert result["decision"] == "REJECT"
        assert result["checks"]["title"]["passed"] is False
        assert result["checks"]["title"]["severity"] == "blocking"

    def test_missing_h1_blocking(self):
        html = VALID_HTML.replace("<h1>Main Heading</h1>", "")
        result = evaluate_technical_seo(html)
        assert result["decision"] == "REJECT"
        assert result["checks"]["h1"]["passed"] is False
        assert result["checks"]["h1"]["severity"] == "blocking"

    def test_thin_content_blocking(self):
        html = """<html><head><title>Test</title><meta name="description" content="desc"><link rel="canonical" href="/"></head><body><h1>H1</h1><p>Too short.</p></body></html>"""
        result = evaluate_technical_seo(html)
        assert result["decision"] == "REJECT"
        assert result["checks"]["content_substance"]["passed"] is False

    def test_noindex_blocking(self):
        html = VALID_HTML.replace("</head>", '<meta name="robots" content="noindex"></head>')
        result = evaluate_technical_seo(html)
        assert result["decision"] == "REJECT"
        assert result["checks"]["noindex_robots"]["passed"] is False
        assert result["checks"]["noindex_robots"]["severity"] == "blocking"

    def test_soft_404_blocking(self):
        html = """<html><head><title>Error</title></head><body><h1>Page Not Found</h1><p>404 error occurred.</p></body></html>"""
        result = evaluate_technical_seo(html)
        assert result["decision"] == "REJECT"
        assert result["checks"]["soft_404"]["passed"] is False

    def test_no_internal_links_advisory(self):
        html = VALID_HTML.replace('<a href="/internal-link">Internal Link</a>', "").replace('<a href="https://example.com/another-page">Another Internal Link</a>', "")
        result = evaluate_technical_seo(html)
        # Advisory-only warning: decision should be PASS
        assert result["decision"] == "PASS"
        assert result["blocked"] is False
        assert result["checks"]["internal_links"]["passed"] is False
        assert result["checks"]["internal_links"]["severity"] == "advisory"
        assert "internal link" in str(result["warnings"]).lower()

    def test_no_structured_data_advisory(self):
        html = VALID_HTML.replace('<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}</script>', "")
        result = evaluate_technical_seo(html)
        # Advisory-only warning: decision should be PASS
        assert result["decision"] == "PASS"
        assert result["blocked"] is False
        assert result["checks"]["structured_data"]["passed"] is False
        assert result["checks"]["structured_data"]["severity"] == "advisory"
        assert "structured data" in str(result["warnings"]).lower()

    def test_missing_meta_description_advisory(self):
        html = VALID_HTML.replace('<meta name="description" content="Test meta description here.">', "")
        result = evaluate_technical_seo(html)
        # Advisory-only warning: decision should be PASS
        assert result["decision"] == "PASS"
        assert result["blocked"] is False
        assert result["checks"]["meta_description"]["passed"] is False
        assert result["checks"]["meta_description"]["severity"] == "advisory"
        assert "meta description" in str(result["warnings"]).lower()

    def test_artifact_http_status(self):
        artifact = {"http_status": 200}
        result = evaluate_technical_seo(VALID_HTML, artifact=artifact)
        assert result["checks"]["http_status"]["passed"] is True

        artifact = {"http_status": 404}
        result = evaluate_technical_seo(VALID_HTML, artifact=artifact)
        assert result["checks"]["http_status"]["passed"] is False
        assert result["checks"]["http_status"]["severity"] == "blocking"

    def test_canonical_invalid_href(self):
        html = VALID_HTML.replace('href="https://example.com/test-page"', 'href="javascript:void(0)"')
        result = evaluate_technical_seo(html)
        assert result["checks"]["canonical"]["passed"] is False