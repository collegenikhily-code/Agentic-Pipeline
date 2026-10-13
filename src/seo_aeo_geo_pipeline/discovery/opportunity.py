"""Convert KeywordCluster → PageOpportunity.

Deterministic page-type recommendation based on available evidence.
No LLM, no paid APIs.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from .models import KeywordCluster, KeywordObservation, PageOpportunity


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _opportunity_id(primary_keyword: str) -> str:
    slug = _slugify(primary_keyword)
    h = hashlib.sha256(slug.encode()).hexdigest()[:8]
    return f"opp-{slug[:40]}-{h}"


def _detect_page_type(
    cluster: KeywordCluster,
    observations: list[KeywordObservation],
) -> str:
    """Recommend a page type based on multi-signal classification.

    Uses keyword semantics, intent, entities, SERP features, and competitor
    evidence together — never relies on a single signal.
    """
    intent = cluster.dominant_intent
    keywords_lower = [k.lower() for k in cluster.keywords]
    all_text = " ".join(keywords_lower)
    primary = cluster.primary_keyword.lower()
    serp = [f.lower() for f in cluster.serp_features]
    competitors = cluster.competitor_pages

    # ── Comparison / Alternatives ──────────────────────────────────────────
    comparison_signals = ["vs", "versus", "compared", "comparison", "review"]
    if any(s in all_text for s in comparison_signals):
        return "comparison-guide"

    alternative_signals = ["alternative", "alternatives", "similar to", "like "]
    if any(s in all_text for s in alternative_signals):
        return "alternatives-page"

    best_top_signals = ["best", "top", "best ", "top "]
    if any(s in primary for s in best_top_signals):
        return "comparison-guide"

    # Transactional "buy" queries → comparison-guide (shopping intent)
    if intent == "commercial" and "buy" in primary:
        return "comparison-guide"

    # ── Use-Case / Capability / Workflow / Integration ─────────────────────
    # Multi-signal: keyword semantics + any intent (not just commercial)
    use_case_keywords = [
        "use case", "use cases", "workflow", "automate", "automation",
        "integrate", "integration", "integrations",
        "for teams", "for business", "for agencies", "for startups", "for enterprise",
        "capabilities", "features of", "what can", "what does",
        "streamline", "scale up",
    ]
    integration_keywords = [
        "integration", "integrates", "connect", "sync", "api",
        "zapier", "webhook", "plugin", "add-on", "extension",
    ]
    workflow_keywords = [
        "workflow", "pipeline", "step by step",
        "automate", "automation", "trigger", "batch", "bulk",
    ]

    # Word-boundary matching to avoid substring false positives
    # e.g. "manage" in "facebook business manager" should not match
    def _has_signal(text: str, keywords: list[str]) -> bool:
        for kw in keywords:
            if " " in kw:
                if kw in text:
                    return True
            else:
                if re.search(r'\b' + re.escape(kw) + r'\b', text):
                    return True
        return False

    has_use_case_signal = _has_signal(all_text, use_case_keywords)
    has_integration_signal = _has_signal(all_text, integration_keywords)
    has_workflow_signal = _has_signal(all_text, workflow_keywords)

    # Strong use-case signals in keyword → use-case-capability regardless of intent
    # Integration signals also route here (integration-page is a future archetype,
    # not yet implemented with its own template/schema/renderer).
    if has_use_case_signal or has_integration_signal or has_workflow_signal:
        return "use-case-capability"

    # SERP features indicating product/comparison pages
    product_serp = ["shopping", "product", "price", "pricing"]
    if any(s in " ".join(serp) for s in product_serp):
        if intent in ("commercial", "transactional"):
            return "use-case-capability"

    # ── How-to / Instructional / Guide ─────────────────────────────────────
    how_to_signals = ["how to", "guide", "tutorial", "steps", "learn"]
    if intent == "informational" and any(s in all_text for s in how_to_signals):
        return "guide"

    # ── Entity / Reference ─────────────────────────────────────────────────
    # Only match clear entity/definition queries when no competitors exist
    entity_signals = [
        "definition", "meaning", "who is", "when did",
        "history of", "overview of",
    ]
    if not competitors and any(s in all_text for s in entity_signals):
        return "reference-page"

    # ── Intent-based defaults ──────────────────────────────────────────────
    if intent == "transactional":
        return "product-page"
    if intent == "commercial":
        return "comparison-guide"
    if intent == "informational":
        return "guide"

    return "reference-page"


def _build_opportunity_reason(
    cluster: KeywordCluster,
    page_type: str,
) -> str:
    """Generate a human-readable reason for this opportunity."""
    vol = cluster.total_search_volume
    diff = cluster.avg_difficulty
    n_competitors = len(cluster.competitor_pages)
    n_keywords = len(cluster.keywords)

    parts = [f"Cluster of {n_keywords} keywords with {vol} combined monthly volume"]

    if diff > 0:
        parts.append(f"difficulty {diff:.0f}")

    if n_competitors > 0:
        parts.append(f"{n_competitors} competitor ranking URLs")

    if cluster.dominant_intent:
        parts.append(f"intent: {cluster.dominant_intent}")

    parts.append(f"recommended type: {page_type}")

    return ". ".join(parts) + "."


def cluster_to_opportunity(
    cluster: KeywordCluster,
    observations: list[KeywordObservation] | None = None,
) -> PageOpportunity:
    """Convert a KeywordCluster into a PageOpportunity."""
    page_type = _detect_page_type(cluster, observations or [])
    slug = _slugify(cluster.primary_keyword)

    # Secondary keywords: all except primary
    secondary = [k for k in cluster.keywords if k != cluster.primary_keyword]

    return PageOpportunity(
        opportunity_id=_opportunity_id(cluster.primary_keyword),
        primary_keyword=cluster.primary_keyword,
        secondary_keywords=secondary,
        intent=cluster.dominant_intent,
        search_volume=cluster.total_search_volume,
        difficulty=cluster.avg_difficulty,
        competitor_pages=cluster.competitor_pages,
        questions=cluster.supporting_questions,
        serp_features=cluster.serp_features,
        recommended_page_type=page_type,
        recommended_slug=f"/{slug}",
        opportunity_reason=_build_opportunity_reason(cluster, page_type),
    )


def clusters_to_opportunities(
    clusters: list[KeywordCluster],
    observations: list[KeywordObservation] | None = None,
) -> list[PageOpportunity]:
    """Convert multiple KeywordClusters into PageOpportunities."""
    opps = [cluster_to_opportunity(c, observations) for c in clusters]
    opps.sort(key=lambda o: o.search_volume, reverse=True)
    return opps
