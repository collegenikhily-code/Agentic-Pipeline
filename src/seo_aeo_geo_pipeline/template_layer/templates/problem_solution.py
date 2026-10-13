"""Template specifications for the problem-solution family."""

from __future__ import annotations

from ..template_spec import TemplateSpec

product_how_to_spec = TemplateSpec(
    name="product-how-to",
    family="problem-solution",
    description="Informational content establishing topical expertise",
    prompt_sections=[
        "h1_headline",
        "introduction",
        "background",
        "steps_bullet_list",
        "pro_tips",
        "common_mistakes",
        "next_steps",
        "faq_section",
    ],
    output_schema=[
        "h1",
        "introduction",
        "background",
        "steps",
        "pro_tips",
        "common_mistakes",
        "next_steps",
        "faq",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
        "action": "",
        "product": "",
    },
)

problem_solution_spec = TemplateSpec(
    name="problem-solution",
    family="problem-solution",
    description="Problem/solution framework for informational content",
    prompt_sections=[
        "h1_headline",
        "problem_statement",
        "solution_overview",
        "implementation_steps",
        "expected_outcomes",
        "faq_section",
        "closing",
    ],
    output_schema=[
        "h1",
        "problem_statement",
        "solution_overview",
        "implementation_steps",
        "expected_outcomes",
        "faq",
        "closing",
    ],
    default_params={
        "site_name": "",
        "industry": "",
        "brand_voice": "",
    },
)
