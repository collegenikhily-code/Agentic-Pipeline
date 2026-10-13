"""Deterministic keyword clustering.

Groups keywords into clusters based on:
1. Search intent compatibility
2. Ranking URL overlap (strongest signal)
3. Keyword text similarity
4. Competitor page overlap

No LLM, no embeddings, no paid APIs.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Optional

from .models import KeywordCluster, KeywordObservation


def _keyword_set_key(keyword: str) -> str:
    """Produce a canonical form for similarity comparison."""
    return " ".join(sorted(keyword.lower().split()))


def _jaccard_similarity(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _tokens(text: str) -> set[str]:
    return set(text.lower().split())


def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def _cluster_id(primary_keyword: str) -> str:
    slug = primary_keyword.lower().strip()
    slug = " ".join(slug.split())
    slug = slug.replace(" ", "-")
    h = hashlib.sha256(slug.encode()).hexdigest()[:8]
    return f"kc-{slug[:40]}-{h}"


def cluster_keywords(
    observations: list[KeywordObservation],
    min_overlap_ratio: float = 0.3,
) -> list[KeywordCluster]:
    """Cluster keyword observations into groups sharing the same page opportunity.

    Strategy:
    1. Group by dominant intent first (informational vs commercial vs transactional).
    2. Within each intent group, merge keywords that share ranking URLs or
       competitor pages.
    3. Use keyword text similarity as a secondary merge signal.

    Returns a list of KeywordCluster objects sorted by total search volume.
    """
    if not observations:
        return []

    intent_groups: dict[str, list[KeywordObservation]] = defaultdict(list)
    for obs in observations:
        intent = obs.intent or "unknown"
        intent_groups[intent].append(obs)

    all_clusters: list[KeywordCluster] = []

    for intent, intent_obs in intent_groups.items():
        clusters = _cluster_by_intent(intent, intent_obs, min_overlap_ratio)
        all_clusters.extend(clusters)

    all_clusters.sort(key=lambda c: c.total_search_volume, reverse=True)
    return all_clusters


def _cluster_by_intent(
    intent: str,
    observations: list[KeywordObservation],
    min_overlap_ratio: float,
) -> list[KeywordCluster]:
    """Within a single intent group, cluster by URL/competitor overlap."""
    url_index: dict[str, set[int]] = defaultdict(set)
    for i, obs in enumerate(observations):
        if obs.ranking_url:
            url_index[obs.ranking_url].add(i)

    # Union-Find for merging keywords that share URLs
    parent = list(range(len(observations)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    # Merge keywords that share a ranking URL
    for url, indices in url_index.items():
        indices_list = sorted(indices)
        for i in range(1, len(indices_list)):
            union(indices_list[0], indices_list[i])

    # Additional merge: keywords with high text overlap within same intent
    token_sets = [_tokens(obs.keyword) for obs in observations]
    for i in range(len(observations)):
        for j in range(i + 1, len(observations)):
            if find(i) == find(j):
                continue
            sim = _jaccard_similarity(token_sets[i], token_sets[j])
            if sim >= 0.6:
                union(i, j)

    # Group by root
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(observations)):
        groups[find(i)].append(i)

    clusters: list[KeywordCluster] = []
    for root, member_indices in groups.items():
        members = [observations[i] for i in member_indices]
        cluster = _build_cluster(intent, members)
        clusters.append(cluster)

    return clusters


def _build_cluster(
    intent: str,
    members: list[KeywordObservation],
) -> KeywordCluster:
    """Build a KeywordCluster from a group of observations."""
    # Select primary keyword: highest volume
    members_sorted = sorted(members, key=lambda o: o.search_volume, reverse=True)
    primary = members_sorted[0].keyword

    keywords = list({m.keyword for m in members})
    total_volume = sum(m.search_volume for m in members)
    difficulties = [m.difficulty for m in members if m.difficulty > 0]
    avg_diff = sum(difficulties) / len(difficulties) if difficulties else 0.0

    # Collect unique competitor pages
    competitor_urls = list({m.ranking_url for m in members if m.ranking_url})
    competitor_domains = list({m.ranking_domain for m in members if m.ranking_domain})

    # Collect SERP features
    all_features: set[str] = set()
    for m in members:
        all_features.update(m.serp_features)

    return KeywordCluster(
        cluster_id=_cluster_id(primary),
        primary_keyword=primary,
        keywords=keywords,
        dominant_intent=intent,
        total_search_volume=total_volume,
        avg_difficulty=avg_diff,
        competitor_pages=competitor_urls,
        serp_features=sorted(all_features),
    )
