"""Relevance retrieval: find competitor pages relevant to an SEO opportunity."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

from .models import CompetitorEvidence, CrawledPage


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenization."""
    return re.findall(r"\w+", text.lower())


def _tfidf_score(query_tokens: list[str], doc_tokens: list[str]) -> float:
    """Simple TF-IDF-like relevance score between query and document."""
    if not query_tokens or not doc_tokens:
        return 0.0

    doc_counter = Counter(doc_tokens)
    doc_len = len(doc_tokens)

    score = 0.0
    for token in set(query_tokens):
        tf = doc_counter.get(token, 0) / max(doc_len, 1)
        # Simple IDF-like weight: rare in query = more distinctive
        idf = 1.0  # uniform for now, can be enhanced
        score += tf * idf

    return score


def _compute_relevance(page: CrawledPage, query: str) -> float:
    """Compute relevance score between a page and an opportunity query."""
    query_tokens = _tokenize(query)

    # Combine text fields with weights
    text_parts = []
    # Title is most important
    text_parts.extend([page.title] * 3)
    # Headings are very important
    text_parts.extend(page.headings * 2)
    # Description matters
    text_parts.append(page.description)
    # Main content
    text_parts.append(page.main_content)
    # FAQ questions and answers
    for faq in page.faq:
        text_parts.append(faq.get("question", ""))
        text_parts.append(faq.get("answer", ""))

    doc_tokens = _tokenize(" ".join(text_parts))
    return _tfidf_score(query_tokens, doc_tokens)


def _extract_relevant_content(page: CrawledPage, query: str, max_chars: int = 2000) -> str:
    """Extract the most relevant portion of page content."""
    query_lower = query.lower()
    query_words = set(query_lower.split())

    # Score each paragraph/sentence by relevance
    sentences = re.split(r"(?<=[.!?])\s+", page.main_content)
    scored = []
    for s in sentences:
        s_lower = s.lower()
        hits = sum(1 for w in query_words if w in s_lower)
        scored.append((hits, len(s), s))

    # Sort by hits (desc), then by length (asc for conciseness)
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Build content from most relevant sentences
    result = []
    total = 0
    for _, _, s in scored:
        if total + len(s) > max_chars:
            break
        result.append(s)
        total += len(s)

    return " ".join(result) if result else page.main_content[:max_chars]


def _extract_relevant_headings(page: CrawledPage, query: str) -> list[str]:
    """Extract headings relevant to the query."""
    query_words = set(query.lower().split())
    relevant = []
    for h in page.headings:
        h_lower = h.lower()
        if any(w in h_lower for w in query_words):
            relevant.append(h)
    # If no specific matches, return first few headings
    if not relevant:
        relevant = page.headings[:3]
    return relevant


def _extract_relevant_claims(page: CrawledPage, query: str) -> list[str]:
    """Extract sentences that make specific claims about features/capabilities."""
    query_words = set(query.lower().split())
    claim_indicators = ["can", "supports", "enables", "provides", "offers",
                        "includes", "features", "automates", "integrates"]

    sentences = re.split(r"(?<=[.!?])\s+", page.main_content)
    claims = []
    for s in sentences:
        s_lower = s.lower()
        has_indicator = any(ind in s_lower for ind in claim_indicators)
        has_query_term = any(w in s_lower for w in query_words)
        if has_indicator and has_query_term and len(s) > 30:
            claims.append(s.strip())
            if len(claims) >= 5:
                break

    return claims


def retrieve_relevant(
    pages: list[CrawledPage],
    query: str,
    top_k: int = 10,
    min_score: float = 0.001,
) -> list[CompetitorEvidence]:
    """Retrieve the most relevant competitor pages for a query.

    Returns a bounded list of CompetitorEvidence sorted by relevance.
    """
    scored = []
    for page in pages:
        if page.error or not page.main_content:
            continue
        score = _compute_relevance(page, query)
        if score >= min_score:
            scored.append((score, page))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    evidence = []
    for score, page in scored[:top_k]:
        evidence.append(CompetitorEvidence(
            competitor=page.competitor,
            url=page.canonical_url or page.url,
            page_type=page.page_type,
            relevant_content=_extract_relevant_content(page, query),
            relevant_headings=_extract_relevant_headings(page, query),
            relevant_claims=_extract_relevant_claims(page, query),
            relevance_score=round(score, 4),
            crawled_at=page.crawled_at,
        ))

    return evidence
