"""Normalize raw SE Ranking responses into internal models.

Converts external API schemas into KeywordObservation and CompetitorPage.
Handles missing fields, null values, unexpected types, and malformed records.
Never crashes the entire run on a single bad record.
"""

from __future__ import annotations

from typing import Any, Optional

from .models import CompetitorPage, KeywordObservation


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return str(val).strip()


def _normalize_intent(raw_intents: Any) -> str:
    """Convert intent array or string to a single dominant intent."""
    if isinstance(raw_intents, list) and raw_intents:
        first = str(raw_intents[0]).strip().upper()
        mapping = {
            "I": "informational",
            "C": "commercial",
            "T": "transactional",
            "L": "local",
            "N": "navigational",
        }
        return mapping.get(first, first.lower())
    if isinstance(raw_intents, str) and raw_intents.strip():
        first = raw_intents.strip().upper()[:1]
        mapping = {
            "I": "informational",
            "C": "commercial",
            "T": "transactional",
            "L": "local",
            "N": "navigational",
        }
        return mapping.get(first, raw_intents.strip().lower())
    return ""


def _normalize_serp_features(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(f) for f in raw if f]


def normalize_keyword_record(
    record: dict[str, Any],
    source_domain: str = "",
    source: str = "se_ranking",
) -> Optional[KeywordObservation]:
    """Normalize a single SE Ranking keyword record.

    Returns None if the record is too malformed to use.
    Never raises.
    """
    try:
        keyword = _safe_str(record.get("keyword"))
        if not keyword:
            return None

        url = _safe_str(record.get("url"))
        position = record.get("position")
        ranking_position = _safe_int(position) if position is not None else None

        return KeywordObservation(
            keyword=keyword,
            search_volume=_safe_int(record.get("volume")),
            difficulty=_safe_int(record.get("difficulty")),
            cpc=_safe_float(record.get("cpc")),
            competition=_safe_float(record.get("competition")),
            intent=_normalize_intent(record.get("intents")),
            serp_features=_normalize_serp_features(record.get("serp_features")),
            ranking_domain=_safe_str(record.get("base_domain")) or source_domain,
            ranking_url=url,
            ranking_position=ranking_position,
            our_position=None,
            source=source,
        )
    except Exception:
        return None


def normalize_keywords_response(
    response: dict[str, Any] | list[dict[str, Any]],
    source_domain: str = "",
    source: str = "se_ranking",
) -> list[KeywordObservation]:
    """Normalize a full /v1/domain/keywords response.

    Handles both shapes observed from SE Ranking:
    - A direct list of keyword dicts (actual /v1/domain/keywords)
    - A dict with {"keywords": [...]} or {"result": {...}}

    Returns a list of successfully parsed KeywordObservation objects.
    Skips malformed records.
    """
    results: list[KeywordObservation] = []

    # Direct list response (actual SE Ranking /v1/domain/keywords shape)
    if isinstance(response, list):
        raw_keywords = response
    elif isinstance(response, dict):
        raw_keywords = response.get("keywords") or response.get("result") or []
        if isinstance(raw_keywords, dict):
            raw_keywords = raw_keywords.get("keywords", [])
    else:
        raw_keywords = []

    for record in raw_keywords:
        if not isinstance(record, dict):
            continue
        obs = normalize_keyword_record(record, source_domain=source_domain, source=source)
        if obs is not None:
            results.append(obs)
    return results


def normalize_overlap_response(
    response: dict[str, Any] | list[dict[str, Any]],
    our_domain: str = "",
    competitor_domain: str = "",
) -> dict[str, list[KeywordObservation]]:
    """Normalize a /v1/domain/keywords/overlap response.

    Returns {"only_our": [...], "only_competitor": [...], "common": [...]}

    Handles both dict and list response shapes.
    """
    result: dict[str, list[KeywordObservation]] = {
        "only_our": [],
        "only_competitor": [],
        "common": [],
    }

    # If the response is a list, treat it as a flat keyword list (no gap data)
    if isinstance(response, list):
        for record in response:
            if not isinstance(record, dict):
                continue
            obs = normalize_keyword_record(record, source="se_ranking")
            if obs is not None:
                result["common"].append(obs)
        return result

    for key, label in [
        ("only_domain1", "only_our"),
        ("only_domain2", "only_competitor"),
        ("common", "common"),
    ]:
        raw_list = response.get(key) or []
        if isinstance(raw_list, dict):
            raw_list = raw_list.get("keywords", [])
        for record in raw_list:
            if not isinstance(record, dict):
                continue
            obs = normalize_keyword_record(record, source=source_label(label))
            if obs is not None:
                result[label].append(obs)

    return result


def source_label(label: str) -> str:
    mapping = {
        "only_our": "se_ranking_gap_ours",
        "only_competitor": "se_ranking_gap_competitor",
        "common": "se_ranking_common",
    }
    return mapping.get(label, "se_ranking")


def normalize_related_keywords(
    response: dict[str, Any] | list[dict[str, Any]],
) -> list[KeywordObservation]:
    """Normalize /v1/keywords/related response.

    Handles both dict and list response shapes.
    """
    results: list[KeywordObservation] = []
    if isinstance(response, list):
        raw_keywords = response
    elif isinstance(response, dict):
        raw_keywords = response.get("keywords") or []
    else:
        raw_keywords = []
    for record in raw_keywords:
        if not isinstance(record, dict):
            continue
        obs = normalize_keyword_record(record, source="se_ranking_related")
        if obs is not None:
            results.append(obs)
    return results


def normalize_question_keywords(
    response: dict[str, Any] | list[dict[str, Any]],
) -> list[KeywordObservation]:
    """Normalize /v1/keywords/questions response.

    Handles both dict and list response shapes.
    """
    results: list[KeywordObservation] = []
    if isinstance(response, list):
        raw_keywords = response
    elif isinstance(response, dict):
        raw_keywords = response.get("keywords") or []
    else:
        raw_keywords = []
    for record in raw_keywords:
        if not isinstance(record, dict):
            continue
        obs = normalize_keyword_record(record, source="se_ranking_questions")
        if obs is not None:
            results.append(obs)
    return results


def build_keyword_page_map(
    observations: list[KeywordObservation],
) -> dict[str, list[KeywordObservation]]:
    """Build a mapping from ranking URL → keywords that rank on it.

    This is the core Keyword → Competitor Ranking URL mapping.
    """
    url_map: dict[str, list[KeywordObservation]] = {}
    for obs in observations:
        url = obs.ranking_url
        if not url:
            continue
        url_map.setdefault(url, []).append(obs)
    return url_map


def build_competitor_pages(
    observations: list[KeywordObservation],
) -> list[CompetitorPage]:
    """Group keyword observations into CompetitorPage objects by URL."""
    url_map = build_keyword_page_map(observations)
    pages: list[CompetitorPage] = []

    for url, obs_list in url_map.items():
        if not obs_list:
            continue

        domain = obs_list[0].ranking_domain
        keywords = [o.keyword for o in obs_list]
        positions = {
            o.keyword: o.ranking_position
            for o in obs_list
            if o.ranking_position is not None
        }
        volumes = [o.search_volume for o in obs_list]
        difficulties = [o.difficulty for o in obs_list]

        pages.append(
            CompetitorPage(
                domain=domain,
                url=url,
                keywords=keywords,
                ranking_positions=positions,
                avg_volume=sum(volumes) / len(volumes) if volumes else 0.0,
                avg_difficulty=sum(difficulties) / len(difficulties) if difficulties else 0.0,
            )
        )

    pages.sort(key=lambda p: p.avg_volume, reverse=True)
    return pages
