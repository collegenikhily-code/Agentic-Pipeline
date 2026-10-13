"""Template Layer - Template registry, selection, and HyperText integration."""

from seo_aeo_geo_pipeline.template_layer.registry import (
    TemplateRegistry,
    TemplateSpec,
    register_all_templates,
)
from seo_aeo_geo_pipeline.template_layer.template_selector import TemplateSelector
from seo_aeo_geo_pipeline.template_layer.hypertext_selector import (
    HyperTextSelectorAdapter,
    HyperTextClient,
    TemplateSelectorFallback,
    HyperTextSelectionInput,
    HyperTextSelectionResult,
    TemplateSelectionContext,
    create_hypertext_adapter,
)

__all__ = [
    "TemplateRegistry",
    "TemplateSpec",
    "register_all_templates",
    "TemplateSelector",
    "HyperTextSelectorAdapter",
    "HyperTextClient",
    "TemplateSelectorFallback",
    "HyperTextSelectionInput",
    "HyperTextSelectionResult",
    "TemplateSelectionContext",
    "create_hypertext_adapter",
]