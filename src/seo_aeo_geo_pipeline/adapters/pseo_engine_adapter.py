"""pSEO Engine adapter - M2 dynamic template layer integration.

M1: Prints generation prompt without calling LiteLLM API.
M2: Uses TemplateSelector driven by PageSpec.page_type for dynamic template assignment.
No Anthropic/OpenAI keys required. Generation interface is defined
but not invoked. Real generation is Milestone 3+.
"""

from __future__ import annotations

from typing import Any, Optional

from seo_aeo_geo_pipeline.template_layer.registry import TemplateRegistry, register_all_templates
from seo_aeo_geo_pipeline.template_layer.template_selector import TemplateSelector
from seo_aeo_geo_pipeline.config import Settings
from seo_aeo_geo_pipeline.template_layer.template_spec import load_template_body


def discover(config_path: str, dry_run: bool = True) -> dict[str, Any]:
    """Run keyword discovery with matrix expansion + source collectors.

    M1/M2: Returns empty opportunities. Real discovery uses SE Ranking integration.
    """
    if dry_run:
        return {
            "opportunities": [],
            "dry_run": True,
            "note": "Real discovery uses scripts/discover_opportunities.py with SE Ranking",
        }
    raise NotImplementedError("Real discovery: use scripts/discover_opportunities.py")


def _load_template_registry() -> TemplateRegistry:
    """Load and register all TemplateSpec entries."""
    registry = TemplateRegistry()
    register_all_templates(registry)
    return registry


def _select_template_for_pagespec(page_spec: dict, registry: TemplateRegistry) -> str:
    """Select a template name from PageSpec using TemplateSelector.
    
    The selector is driven by PageSpec.page_type, enabling dynamic template
    assignment based on intent/page type rather than hardcoding templates per page.
    """
    selector = TemplateSelector(registry, Settings())
    template_spec = selector.select_for_page_spec(page_spec)
    if template_spec:
        return template_spec.name
    return "comparison-guide"


def _build_research_context(keyword: str, page_spec: dict) -> str:
    """Build research context text for prompt injection from PageSpec entity_data."""
    research_parts = []
    entity_data = page_spec.get("entity_data", {}) if page_spec else {}
    if entity_data.get("site_name"):
        research_parts.append(f"Site: {entity_data['site_name']}")
    if entity_data.get("industry"):
        research_parts.append(f"Industry: {entity_data['industry']}")
    questions = page_spec.get("questions", []) if page_spec else []
    for q in questions[:3]:
        research_parts.append(f"  - {q}")
    diff_strategy = page_spec.get("differentiation_strategy", "") if page_spec else ""
    if diff_strategy:
        research_parts.append(f"Differentiation: {diff_strategy}")
    return "\n".join(research_parts) if research_parts else ""


def generate_draft(config_path: str, keyword: str, page_spec: dict | None, dry_run: bool = True) -> dict[str, Any]:
    """Generate a draft article for a keyword with dynamic template selection.
    
    M1/M2: Uses TemplateSelector to choose template based on PageSpec.page_type.
    The workflow: Research → PageSpec → Template → pSEO Engine → Page Artifact.
    
    Args:
        config_path: Path to pSEO Engine config YAML
        keyword: Target keyword for content generation
        page_spec: PageSpec dictionary with page_type, entity_data, questions, etc.
        dry_run: If True, prints prompt without calling LiteLLM API
    
    Returns:
        Draft dict with status, prompt, template, and generated_content (None in dry-run)
    """
    if page_spec:
        registry = _load_template_registry()
        template_name = _select_template_for_pagespec(page_spec, registry)
    else:
        template_name = "comparison-guide"
    
    if dry_run:
        template_body = load_template_body(template_name)
        entity_data = page_spec.get("entity_data", {}) if page_spec else {}
        compliance_rules = entity_data.get("compliance_rules", [])
        
        prompt = template_body.format(
            site_name=entity_data.get("site_name", ""),
            industry=entity_data.get("industry", ""),
            brand_voice=entity_data.get("brand_voice", ""),
            year=entity_data.get("year", "2026"),
            compliance_rules=compliance_rules,
            research_context=_build_research_context(keyword, page_spec),
        )
        
        return {
            "keyword": keyword,
            "status": "dry_run",
            "prompt": prompt,
            "template": template_name,
            "generated_content": None,
            "page_type": page_spec.get("page_type", "") if page_spec else "",
        }
    
    raise NotImplementedError("Real generation: M3+")


def validate_guardrails(draft: dict, existing_titles: list[str] | None = None) -> dict[str, Any]:
    """Run pSEO Engine guardrail checks on a draft.
    
    M1/M2: Returns mock guardrail report. No actual checking without DB/corpus.
    """
    results = [
        {"check_name": "ai_artifacts", "passed": True, "severity": "blocking"},
        {"check_name": "title_uniqueness", "passed": True, "severity": "blocking"},
        {"check_name": "differentiation", "passed": True, "severity": "blocking"},
        {"check_name": "external_citations", "passed": False, "severity": "blocking"},
        {"check_name": "entity_density", "passed": True, "severity": "blocking"},
        {"check_name": "word_count", "passed": True, "severity": "advisory"},
        {"check_name": "faq_count", "passed": False, "severity": "advisory"},
        {"check_name": "keyword_presence", "passed": True, "severity": "advisory"},
        {"check_name": "section_completeness", "passed": True, "severity": "advisory"},
        {"check_name": "template_required_sections", "passed": True, "severity": "blocking"},
        {"check_name": "structural_repetition", "passed": True, "severity": "blocking"},
        {"check_name": "information_gain", "passed": True, "severity": "blocking"},
        {"check_name": "schema_validation", "passed": True, "severity": "blocking"},
    ]
    
    blocked = not all(r["passed"] for r in results if r["severity"] == "blocking")
    
    return {
        "blocked": blocked,
        "warnings": [],
        "results": results,
    }
