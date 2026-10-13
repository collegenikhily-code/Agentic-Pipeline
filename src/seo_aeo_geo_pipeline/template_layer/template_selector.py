"""TemplateSelector: Selects the appropriate TemplateSpec based on PageSpec page_type.

Selection logic:
- PageSpec.page_type drives template family selection
- Within the family, the highest-priority TemplateSpec is chosen
- Falls back to config-specified default if no match found
- Enables dynamic, data-driven template assignment (not hardcoded per page)
"""

from __future__ import annotations

from typing import Optional

from .template_registry import TemplateRegistry
from ..config import Settings


class TemplateSelector:
    """Selects the appropriate TemplateSpec based on PageSpec page_type.

    The selector is driven by PageSpec.page_type, enabling dynamic template
    assignment based on intent/page type rather than hardcoding templates per
    page. This supports the Research → PageSpec → Template → pSEO Engine → Page
    Artifact workflow.

    Template families map to page types as follows:
    - "comparison"        → comparison guides, vs. articles
    - "alternatives"      → alternatives/roundup articles
    - "best-listicle"     → best-of / listicle posts
    - "role-guide"        → role/use-case guide articles
    - "problem-solution" → problem/solution / how-to content
    - "programmatic-entity" → entity/property pages, programmatic content
    """

    FAMILY_MAP = {
        "comparison": "comparison",
        "alternatives": "alternatives",
        "best-listicle": "best-listicle",
        "role-guide": "role-guide",
        "problem-solution": "problem-solution",
        "programmatic-entity": "programmatic-entity",
        "use-case-capability": "use-case-capability",
    }

    def __init__(self, registry: TemplateRegistry, config: Settings) -> None:
        self.registry = registry
        self.config = config

    def select(self, page_type: str) -> Optional[TemplateSpec]:
        """Select a TemplateSpec based on the given page_type.

        Args:
            page_type: The page_type from PageSpec (e.g. "comparison", "product-how-to")

        Returns:
            The selected TemplateSpec, or None if no match found and no fallback
        """
        family = self.FAMILY_MAP.get(page_type)
        if not family:
            # Try exact match first
            spec = self.registry.get(page_type)
            if spec:
                return spec
            return None

        # Get templates in this family, sorted by priority (highest first)
        templates = self.registry.get_by_family(family)
        if not templates:
            return None

        # Sort by priority descending, then by registration order
        selected = max(templates, key=lambda t: (t.priority, self._order_index(t.name)))
        return selected

    def _order_index(self, name: str) -> int:
        """Get the registration order index for a template name."""
        try:
            return self.registry._order.index(name)
        except ValueError:
            return -1

    def select_for_page_spec(self, page_spec: dict) -> Optional[TemplateSpec]:
        """Select template from a PageSpec dict.

        Args:
            page_spec: PageSpec dictionary, expected to have a "page_type" key

        Returns:
            Selected TemplateSpec or None
        """
        page_type = page_spec.get("page_type", "") if isinstance(page_spec, dict) else ""
        return self.select(page_type)

    @classmethod
    def from_config(cls, registry: TemplateRegistry, config: Settings) -> "TemplateSelector":
        """Factory method to create TemplateSelector from config."""
        return cls(registry, config)
