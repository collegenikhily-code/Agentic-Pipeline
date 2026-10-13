"""Template registry initialization - registers all TemplateSpec entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TemplateSpec:
    """Specification for a content generation template."""

    name: str
    family: str
    description: str
    prompt_sections: List[str]
    output_schema: List[str]
    default_params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "description": self.description,
            "prompt_sections": self.prompt_sections,
            "output_schema": self.output_schema,
            "default_params": self.default_params,
            "priority": self.priority,
        }


class TemplateRegistry:
    """Registry that holds and manages registered TemplateSpec entries."""

    def __init__(self) -> None:
        self._by_name: Dict[str, TemplateSpec] = {}
        self._by_family: Dict[str, List[TemplateSpec]] = {}
        self._order: List[str] = []

    def register(self, spec: TemplateSpec) -> None:
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
        return self._by_name.get(name)

    def get_by_family(self, family: str) -> List[TemplateSpec]:
        return self._by_family.get(family, [])

    def list_all(self) -> List[TemplateSpec]:
        return [self._by_name[name] for name in self._order if name in self._by_name]

    def families(self) -> List[str]:
        return list(self._by_family.keys())


def register_all_templates(registry: TemplateRegistry) -> None:
    """Register all TemplateSpec entries with the given registry."""
    from .templates.comparison import comparison_guide_spec, alternatives_spec
    from .templates.programmatic import reference_entry_spec, entity_profile_spec
    from .templates.role_guide import role_guide_spec, use_case_guide_spec
    from .templates.problem_solution import product_how_to_spec, problem_solution_spec
    from .templates.best_listicle import best_listicle_spec, gift_guide_spec

    # Comparison family
    registry.register(comparison_guide_spec)
    registry.register(alternatives_spec)

    # Programmatic-entity family
    registry.register(reference_entry_spec)
    registry.register(entity_profile_spec)

    # Role-guide family
    registry.register(role_guide_spec)
    registry.register(use_case_guide_spec)

    # Problem-solution family
    registry.register(product_how_to_spec)
    registry.register(problem_solution_spec)

    # Best-listicle family
    registry.register(best_listicle_spec)
    registry.register(gift_guide_spec)