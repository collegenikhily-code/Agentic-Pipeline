"""pseolint adapter - M1 dry-run stub only.

M1: Audits build directory or structured draft data.
No npx pseolint required for unit tests. Real CLI integration M2+.
"""

from __future__ import annotations
from typing import Any


def audit_build_directory(directory: str) -> dict[str, Any]:
    """Audit generated pages in a build directory.
    
    M1: Returns mock verdict. Real pseolint CLI integration M2+.
    """
    return {
        "verdict": "ready",
        "risk": 23,
        "categories": {
            "Integrity": "ready",
            "Discoverability": "ready",
            "Citation": "ready",
            "Data": "ready",
        },
        "templates": [],
    }


def audit_draft_data(structured_data: dict) -> dict[str, Any]:
    """Audit a draft's structured data directly.
    
    M1: Returns mock findings. Real @pseolint/core SDK integration M2+.
    """
    return {
        "verdict": "caution",
        "risk": 45,
        "categories": {
            "Integrity": "caution",
            "Discoverability": "ready",
            "Citation": "caution",
            "Data": "ready",
        },
        "top_fixes": [
            "Add external citations to satisfy E-E-A-T",
            "Improve entity density for AI citability",
        ],
    }