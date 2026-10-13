"""Template specifications for the programmatic-entity family."""

from __future__ import annotations

from ..template_spec import TemplateSpec

reference_entry_spec = TemplateSpec(
    name="reference-entry",
    family="programmatic-entity",
    description="Entity/property reference pages with structured data",
    prompt_sections=[
        "h1_headline",
        "quick_answer",
        "what_this_means",
        "common_confusions",
        "why_it_matters",
        "key_signals",
        "faq_section",
        "closing",
    ],
    output_schema=[
        "h1",
        "quick_answer",
        "what_this_means",
        "common_confusions",
        "why_it_matters",
        "key_signals",
        "faq",
        "closing",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
    },
)

entity_profile_spec = TemplateSpec(
    name="entity-profile",
    family="programmatic-entity",
    description="Programmatic entity profile pages",
    prompt_sections=[
        "h1_headline",
        "introduction",
        "key_attributes",
        "specifications",
        "use_cases",
        "faq_section",
        "closing",
    ],
    output_schema=[
        "h1",
        "introduction",
        "key_attributes",
        "specifications",
        "use_cases",
        "faq",
        "closing",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
    },
)
