"""HTML content extraction using BeautifulSoup."""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from .models import CrawledPage


def _clean_text(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _extract_headings(soup: BeautifulSoup) -> list[str]:
    """Extract all heading texts."""
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = _clean_text(tag.get_text())
        if text:
            headings.append(text)
    return headings


def _extract_meta(soup: BeautifulSoup) -> tuple[str, str]:
    """Extract title and description from meta tags."""
    title = ""
    desc = ""

    title_tag = soup.find("title")
    if title_tag:
        title = _clean_text(title_tag.get_text())

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and isinstance(meta_desc, Tag):
        desc = meta_desc.get("content", "")

    return title, desc


def _extract_canonical(soup: BeautifulSoup) -> str:
    """Extract canonical URL if present."""
    link = soup.find("link", attrs={"rel": "canonical"})
    if link and isinstance(link, Tag):
        return link.get("href", "")
    return ""


def _extract_faq(soup: BeautifulSoup) -> list[dict[str, str]]:
    """Extract FAQ items from structured data or content patterns."""
    faq = []

    # Try JSON-LD FAQPage schema
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "FAQPage":
                for item in data.get("mainEntity", []):
                    q = item.get("name", "")
                    a = ""
                    accepted = item.get("acceptedAnswer", {})
                    if isinstance(accepted, dict):
                        a = accepted.get("text", "")
                    if q and a:
                        faq.append({"question": q, "answer": _clean_text(a)})
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: look for heading + paragraph patterns
    if not faq:
        for h in soup.find_all(["h2", "h3", "h4"]):
            text = _clean_text(h.get_text())
            if text.endswith("?"):
                # Get next sibling paragraph
                next_p = h.find_next_sibling("p")
                if next_p:
                    answer = _clean_text(next_p.get_text())
                    if answer:
                        faq.append({"question": text, "answer": answer})

    return faq


def _extract_main_content(soup: BeautifulSoup) -> str:
    """Extract the main content area, removing nav/footer/header."""
    # Remove non-content elements
    for tag in soup.find_all(["nav", "footer", "header", "aside", "script", "style", "noscript"]):
        tag.decompose()

    # Try to find main content area
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    if main:
        return _clean_text(main.get_text())

    # Fallback: use body
    body = soup.find("body")
    if body:
        return _clean_text(body.get_text())

    return _clean_text(soup.get_text())


def _extract_date(soup: BeautifulSoup, attr: str) -> Optional[str]:
    """Extract published or modified date from meta tags."""
    for name in [attr, f"article:{attr}"]:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and isinstance(tag, Tag):
            content = tag.get("content", "")
            if content:
                return content
    return None


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract internal links from the page."""
    from urllib.parse import urljoin
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        if full.startswith("http"):
            links.append(full)
    return links


def extract_content(page: CrawledPage) -> CrawledPage:
    """Extract structured content from raw HTML in a CrawledPage.

    Modifies the page in-place and returns it.
    """
    html = page.main_content
    if not html or page.error:
        return page

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        page.error = "html_parse_error"
        return page

    # Extract metadata
    page.title, page.description = _extract_meta(soup)
    canonical = _extract_canonical(soup)
    if canonical:
        page.canonical_url = canonical

    # Extract content
    page.headings = _extract_headings(soup)
    page.main_content = _extract_main_content(soup)
    page.faq = _extract_faq(soup)
    page.links = _extract_links(soup, page.url)
    page.published_date = _extract_date(soup, "published_time")
    page.modified_date = _extract_date(soup, "modified_time")

    # Word count and content hash
    page.word_count = len(page.main_content.split())
    page.content_hash = hashlib.sha256(page.main_content.encode("utf-8")).hexdigest()[:16]

    return page
