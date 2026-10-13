"""TemplateRegistry: Registry for managing TemplateSpec entries."""

from __future__ import annotations

from typing import Dict, List, Optional

from .template_spec import TemplateSpec


class TemplateRegistry:
    """Registry that holds and manages registered TemplateSpec entries.

    Supports:
    - Registering templates by name and family
    - Retrieving templates by name
    - Listing templates by family
    - Getting all registered templates
    - Family-based selection filtering
    """

    def __init__(self) -> None:
        self._by_name: Dict[str, TemplateSpec] = {}
        self._by_family: Dict[str, List[TemplateSpec]] = {}
        self._order: List[str] = []  # Preserves registration order per family

    def register(self, spec: TemplateSpec) -> None:
        """Register a TemplateSpec in the registry."""
        if spec.name in self._by_name:
            raise ValueError(f"Template '{spec.name}' already registered")
        self._by_name[spec.name] = spec
        family = spec.family
        if family not in self._by_family:
            self._by_family[family] = []
        self._by_family[family].append(spec)
        if spec.name not in self._order:
            self._order.append(spec.name)

    def get(self, name: str) -> Optional[TemplateSpec]:
        """Retrieve a TemplateSpec by name."""
        return self._by_name.get(name)

    def get_by_family(self, family: str) -> List[TemplateSpec]:
        """Retrieve all TemplateSpecs in a given family."""
        return self._by_family.get(family, [])

    def list_all(self) -> List[TemplateSpec]:
        """Return all registered TemplateSpecs in registration order."""
        return [self._by_name[name] for name in self._order if name in self._by_name]

    def families(self) -> List[str]:
        """Return list of registered template families."""
        return list(self._by_family.keys())

    def unregister(self, name: str) -> None:
        """Unregister a TemplateSpec by name."""
        if name not in self._by_name:
            raise ValueError(f"Template '{name}' not found")
        spec = self._by_name.pop(name)
        family = spec.family
        if family in self._by_family and spec.name in self._by_family[family]:
            self._by_family[family].remove(spec)
        self._order = [n for n in self._order if n != name]
