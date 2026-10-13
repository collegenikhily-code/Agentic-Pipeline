"""Technical SEO gate — deterministic checks on rendered HTML + artifact metadata.

Prevents technically invalid pages from reaching publish. Operates only on
rendered output; does not duplicate pSEO/AEO/GEO content validation.

Checks (deterministic, no external calls):
  - HTTP/status representation (from artifact metadata when available)
  - canonical presence and validity
  - accidental noindex/robots blocking
  - title presence
  - meta description presence
  - H1 presence
  - rendered HTML has substantive content
  - internal-link presence/validity
  - structured-data presence and basic validity (JSON-LD in HTML or schema in artifact)
  - sitemap/indexability readiness (summary of title+meta+noindex)
  - obvious soft-404/thin-render failure

Result shape:
  {
    "decision": "PASS" | "REPAIR" | "REJECT",
    "blocked": bool,
    "checks": {check_name: {"passed": bool, "severity": "blocking"|"advisory", "message": str}},
    "warnings": [str, ...],
  }
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse


# Minimum word count in rendered body text to not be considered thin.
MIN_CONTENT_WORDS = 80

# Markers that indicate a soft-404 or error render.
SOFT_404_MARKERS = [
    "page not found",
    "404",
    "not found",
    "error occurred",
    "something went wrong",
    "access denied",
    "forbidden",
]


def _extract_text(html: str) -> str:
    """Strip tags/scripts/styles and return visible text."""
    # Remove script and style blocks entirely
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_json_ld_blocks(html: str) -> list[dict]:
    """Extract and parse JSON-LD script blocks from HTML."""
    blocks: list[dict] = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                blocks.append(parsed)
            elif isinstance(parsed, list):
                blocks.extend(item for item in parsed if isinstance(item, dict))
        except json.JSONDecodeError:
            blocks.append({"__parse_error__": True, "__raw__": raw[:200]})
    return blocks


def _check_noindex(html: str) -> dict:
    """Detect accidental noindex / robots blocking."""
    lower = html.lower()
    # <meta name="robots" content="noindex..."> or nofollow combined with noindex
    meta_robots = re.search(
        r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']*)["\']',
        lower,
    )
    if not meta_robots:
        # content before name
        meta_robots = re.search(
            r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']robots["\']',
            lower,
        )
    if meta_robots:
        content = meta_robots.group(1)
        if "noindex" in content:
            return {
                "passed": False,
                "severity": "blocking",
                "message": f"Meta robots contains noindex: '{content}'",
            }
    # <meta name="googlebot" content="noindex">
    googlebot = re.search(
        r'<meta[^>]+name=["\']googlebot["\'][^>]+content=["\']([^"\']*)["\']',
        lower,
    )
    if googlebot and "noindex" in googlebot.group(1):
        return {
            "passed": False,
            "severity": "blocking",
            "message": f"Meta googlebot contains noindex: '{googlebot.group(1)}'",
        }
    return {
        "passed": True,
        "severity": "blocking",
        "message": "No noindex/robots blocking detected.",
    }


def _check_canonical(html: str) -> dict:
    """Canonical link tag presence and basic validity."""
    match = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if not match:
        # href before rel
        match = re.search(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']',
            html,
            re.IGNORECASE,
        )
    if not match:
        return {
            "passed": False,
            "severity": "advisory",
            "message": "No canonical link tag found.",
        }
    href = match.group(1).strip()
    if not href:
        return {
            "passed": False,
            "severity": "advisory",
            "message": "Canonical link tag has empty href.",
        }
    # Basic validity: absolute URL or root-relative path
    if href.startswith("/") or href.startswith("http://") or href.startswith("https://"):
        return {
            "passed": True,
            "severity": "advisory",
            "message": f"Canonical present: {href[:80]}",
        }
    return {
        "passed": False,
        "severity": "advisory",
        "message": f"Canonical href is not a valid URL or path: {href[:80]}",
    }


def _check_title(html: str) -> dict:
    """Title tag presence and non-empty content."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return {
            "passed": False,
            "severity": "blocking",
            "message": "No <title> tag found.",
        }
    title = match.group(1).strip()
    if not title:
        return {
            "passed": False,
            "severity": "blocking",
            "message": "<title> tag is empty.",
        }
    return {
        "passed": True,
        "severity": "blocking",
        "message": f"Title present ({len(title)} chars).",
    }


def _check_meta_description(html: str) -> dict:
    """Meta description presence and non-empty content."""
    match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
        html,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+name=["\']description["\']',
            html,
            re.IGNORECASE,
        )
    if not match:
        return {
            "passed": False,
            "severity": "advisory",
            "message": "No meta description found.",
        }
    desc = match.group(1).strip()
    if not desc:
        return {
            "passed": False,
            "severity": "advisory",
            "message": "Meta description is empty.",
        }
    return {
        "passed": True,
        "severity": "advisory",
        "message": f"Meta description present ({len(desc)} chars).",
    }


def _check_h1(html: str) -> dict:
    """H1 tag presence and non-empty content."""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return {
            "passed": False,
            "severity": "blocking",
            "message": "No <h1> tag found.",
        }
    h1 = _extract_text(match.group(1)).strip()
    if not h1:
        return {
            "passed": False,
            "severity": "blocking",
            "message": "<h1> tag is empty.",
        }
    return {
        "passed": True,
        "severity": "blocking",
        "message": f"H1 present: {h1[:60]}",
    }


def _check_content_substance(html: str) -> dict:
    """Rendered HTML must have substantive visible content."""
    text = _extract_text(html)
    word_count = len(text.split())
    if word_count < MIN_CONTENT_WORDS:
        return {
            "passed": False,
            "severity": "blocking",
            "message": f"Thin content: {word_count} words (minimum {MIN_CONTENT_WORDS}).",
        }
    return {
        "passed": True,
        "severity": "blocking",
        "message": f"Substantive content: {word_count} words.",
    }


def _check_soft_404(html: str) -> dict:
    """Detect obvious soft-404 / error renders."""
    text = _extract_text(html).lower()
    # Only flag if the page is short AND contains error markers
    word_count = len(text.split())
    found = [m for m in SOFT_404_MARKERS if m in text]
    if found and word_count < 200:
        return {
            "passed": False,
            "severity": "blocking",
            "message": f"Possible soft-404/error render: markers {found}, {word_count} words.",
        }
    return {
        "passed": True,
        "severity": "blocking",
        "message": "No soft-404/error render detected.",
    }


def _check_internal_links(html: str) -> dict:
    """Internal-link presence and validity (href not empty, not just '#')."""
    anchors = re.findall(r'<a[^>]+href=["\']([^"\']*)["\']', html, re.IGNORECASE)
    if not anchors:
        return {
            "passed": False,
            "severity": "advisory",
            "message": "No internal links found in rendered HTML.",
        }
    valid = []
    broken = []
    for href in anchors:
        h = href.strip()
        if not h or h == "#" or h.lower().startswith("javascript:"):
            broken.append(h or "(empty)")
        else:
            valid.append(h)
    if not valid:
        return {
            "passed": False,
            "severity": "advisory",
            "message": f"No valid internal links ({len(broken)} broken/empty).",
        }
    return {
        "passed": True,
        "severity": "advisory",
        "message": f"{len(valid)} valid internal link(s) found.",
    }


def _check_structured_data(html: str, artifact: dict | None) -> dict:
    """Structured-data presence and basic validity (JSON-LD in HTML or schema in artifact)."""
    blocks = _extract_json_ld_blocks(html)
    parse_errors = [b for b in blocks if b.get("__parse_error__")]
    valid_blocks = [b for b in blocks if not b.get("__parse_error__")]

    if valid_blocks:
        # Basic validity: each block has @type or is a list of typed items
        typed = [b for b in valid_blocks if b.get("@type")]
        if typed:
            types = [b.get("@type") for b in typed]
            return {
                "passed": True,
                "severity": "advisory",
                "message": f"JSON-LD present: {len(typed)} typed block(s), types={types[:3]}",
            }
        return {
            "passed": False,
            "severity": "advisory",
            "message": f"JSON-LD present but missing @type ({len(valid_blocks)} block(s)).",
        }

    if parse_errors:
        return {
            "passed": False,
            "severity": "advisory",
            "message": f"JSON-LD present but failed to parse ({len(parse_errors)} error(s)).",
        }

    # Fallback: check artifact for schema_type / structured_data
    if artifact:
        schema_type = artifact.get("schema_type") or artifact.get("seo", {}).get("schema_type")
        if schema_type:
            return {
                "passed": True,
                "severity": "advisory",
                "message": f"No JSON-LD in HTML; artifact declares schema_type={schema_type}.",
            }

    return {
        "passed": False,
        "severity": "advisory",
        "message": "No structured data found in HTML or artifact.",
    }


def _check_http_status(artifact: dict | None) -> dict:
    """HTTP/status representation from artifact metadata when available."""
    if not artifact:
        return {
            "passed": True,
            "severity": "advisory",
            "message": "No artifact metadata; HTTP status not available (pre-publish render).",
        }
    # Look for status indicators in artifact
    status = artifact.get("http_status") or artifact.get("status_code")
    if status is not None:
        try:
            code = int(status)
            if 200 <= code < 300:
                return {
                    "passed": True,
                    "severity": "advisory",
                    "message": f"HTTP status {code} (2xx).",
                }
            return {
                "passed": False,
                "severity": "blocking",
                "message": f"HTTP status {code} is not 2xx.",
            }
        except (TypeError, ValueError):
            pass
    # Generation status field
    gen_status = artifact.get("status")
    if gen_status in ("pending_review", "publish-ready", "blocked", "REPAIR", "REJECT", "PASS"):
        return {
            "passed": True,
            "severity": "advisory",
            "message": f"Artifact generation status: {gen_status} (pre-publish; no live HTTP yet).",
        }
    return {
        "passed": True,
        "severity": "advisory",
        "message": "No HTTP status in artifact (pre-publish render).",
    }


def _check_indexability_readiness(html: str) -> dict:
    """Summary check: page is indexable when title + meta present and no noindex."""
    lower = html.lower()
    has_title = bool(re.search(r"<title[^>]*>\s*\S", html))
    has_meta_desc = bool(
        re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']\S', lower)
        or re.search(r'<meta[^>]+content=["\']\S[^"\']*["\'][^>]+name=["\']description["\']', lower)
    )
    has_noindex = "noindex" in lower
    if has_noindex:
        return {
            "passed": False,
            "severity": "blocking",
            "message": "Not indexable: noindex directive present.",
        }
    if has_title and has_meta_desc:
        return {
            "passed": True,
            "severity": "advisory",
            "message": "Indexability ready: title + meta description present, no noindex.",
        }
    missing = []
    if not has_title:
        missing.append("title")
    if not has_meta_desc:
        missing.append("meta_description")
    return {
        "passed": False,
        "severity": "advisory",
        "message": f"Indexability incomplete: missing {', '.join(missing)}.",
    }


def evaluate_technical_seo(
    html: str,
    artifact: dict | None = None,
) -> dict[str, Any]:
    """Run all technical SEO checks on rendered HTML + optional artifact metadata.

    Returns structured result with decision, blocked, per-check details, warnings.
    """
    checks = {
        "http_status": _check_http_status(artifact),
        "canonical": _check_canonical(html),
        "noindex_robots": _check_noindex(html),
        "title": _check_title(html),
        "meta_description": _check_meta_description(html),
        "h1": _check_h1(html),
        "content_substance": _check_content_substance(html),
        "internal_links": _check_internal_links(html),
        "structured_data": _check_structured_data(html, artifact),
        "indexability_readiness": _check_indexability_readiness(html),
        "soft_404": _check_soft_404(html),
    }

    blocked = any(
        not c["passed"] and c["severity"] == "blocking" for c in checks.values()
    )
    warnings = [
        c["message"]
        for c in checks.values()
        if not c["passed"] and c["severity"] == "advisory"
    ]

    # Per policy: advisory warnings do NOT force REPAIR.
    # Only blocking failures cause REJECT.
    # Correctable blocking issues (if any) would cause REPAIR, but currently
    # all blocking checks in technical SEO are fatal (noindex, missing title, etc.).
    # Advisory warnings are reported but do not change the decision.
    if blocked:
        decision = "REJECT"
    else:
        decision = "PASS"

    return {
        "decision": decision,
        "blocked": blocked,
        "checks": checks,
        "warnings": warnings,
    }
