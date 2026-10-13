"""Template specifications for the comparison family."""

from __future__ import annotations

from ..template_spec import TemplateSpec

comparison_guide_spec = TemplateSpec(
    name="comparison-guide",
    family="comparison",
    description="Buyer's guide and comparison content for purchase decisions",
    prompt_sections=[
        "h1_headline",
        "introduction",
        "criteria_bullet_list",
        "top_picks",
        "comparison_table",
        "how_to_choose",
        "where_to_buy",
        "faq_section",
    ],
    output_schema=[
        "h1",
        "introduction",
        "criteria",
        "top_picks",
        "comparison_table",
        "how_to_choose",
        "where_to_buy",
        "faq",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
        "year": "2026",
    },
)

alternatives_spec = TemplateSpec(
    name="alternatives",
    family="comparison",
    description="Alternatives/roundup content for decision support",
    prompt_sections=[
        "h1_headline",
        "introduction",
        "criteria_bullet_list",
        "top_picks",
        "comparison_table",
        "conclusion",
    ],
    output_schema=[
        "h1",
        "introduction",
        "criteria",
        "top_picks",
        "comparison_table",
        "conclusion",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
        "year": "2026",
    },
)
