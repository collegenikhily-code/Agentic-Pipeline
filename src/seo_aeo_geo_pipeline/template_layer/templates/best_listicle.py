"""Template specifications for the best-listicle family."""

from __future__ import annotations

from ..template_spec import TemplateSpec

best_listicle_spec = TemplateSpec(
    name="best-listicle",
    family="best-listicle",
    description="Best-of / listicle posts for recommendation content",
    prompt_sections=[
        "h1_headline",
        "introduction",
        "selection_criteria",
        "top_picks",
        "comparison_table",
        "honorable_mentions",
        "conclusion",
    ],
    output_schema=[
        "h1",
        "introduction",
        "selection_criteria",
        "top_picks",
        "comparison_table",
        "honorable_mentions",
        "conclusion",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
        "year": "2026",
    },
)

gift_guide_spec = TemplateSpec(
    name="gift-guide",
    family="best-listicle",
    description="Gift guide / roundup content for seasonal/content occasions",
    prompt_sections=[
        "h1_headline",
        "introduction",
        "gift_criteria",
        "top_recommendations",
        "price_ranges",
        "recipient_guides",
        "conclusion",
    ],
    output_schema=[
        "h1",
        "introduction",
        "gift_criteria",
        "top_recommendations",
        "price_ranges",
        "recipient_guides",
        "conclusion",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
        "occasion": "",
    },
)
