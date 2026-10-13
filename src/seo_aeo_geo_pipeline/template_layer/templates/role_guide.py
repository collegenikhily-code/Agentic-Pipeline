"""Template specifications for the role-guide family."""

from __future__ import annotations

from ..template_spec import TemplateSpec

role_guide_spec = TemplateSpec(
    name="role-guide",
    family="role-guide",
    description="Role/use-case guide articles establishing topical expertise",
    prompt_sections=[
        "h1_headline",
        "hook",
        "the_rise",
        "key_use_cases",
        "decision_framework",
        "faq_section",
        "closing_cta",
    ],
    output_schema=[
        "h1",
        "hook",
        "the_rise",
        "key_use_cases",
        "decision_framework",
        "faq",
        "closing_cta",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
    },
)

use_case_guide_spec = TemplateSpec(
    name="use-case-guide",
    family="role-guide",
    description="Use-case guide content for specific audience segments",
    prompt_sections=[
        "h1_headline",
        "introduction",
        "target_audience",
        "primary_use_cases",
        "secondary_use_cases",
        "faq_section",
        "closing",
    ],
    output_schema=[
        "h1",
        "introduction",
        "target_audience",
        "primary_use_cases",
        "secondary_use_cases",
        "faq",
        "closing",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
    },
)
