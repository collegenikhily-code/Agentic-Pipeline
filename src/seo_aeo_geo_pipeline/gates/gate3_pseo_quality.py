"""GATE 3: pSEO Integrity / Content Quality checks."""

from __future__ import annotations
from typing import Any, Literal


def run_guardrails(
    draft_structured_data: dict,
    existing_titles: list[str],
    corpus_texts: list[str],
) -> dict[str, Any]:
    """Run pSEO Engine guardrail checks (13 checks).
    
    M1: Simplified guardrail report. Full 13-check run via pSEO Engine SDK M2+.
    """
    # M1: Basic checks on draft data
    text = " ".join(str(v) for v in draft_structured_data.values() if isinstance(v, str))
    
    results = []
    
    # AI artifacts check
    ai_phrases = ["in conclusion", "it's important to note", "delve into"]
    ai_found = any(phrase in text.lower() for phrase in ai_phrases)
    results.append({
        "check_name": "ai_artifacts",
        "passed": not ai_found,
        "severity": "blocking",
        "message": "AI artifacts detected" if ai_found else "No AI artifacts detected",
    })
    
    # Title uniqueness
    h1 = draft_structured_data.get("h1", "")
    title_unique = all(h1.lower() != t.lower() for t in existing_titles)
    results.append({
        "check_name": "title_uniqueness",
        "passed": title_unique,
        "severity": "blocking",
        "message": "Title is unique" if title_unique else "Duplicate title",
    })
    
    # Differentiation (Jaccard against corpus)
    if corpus_texts:
        article_words = set(text.lower().split())
        min_distance = all(
            len(article_words & set(corpus.lower().split())) / len(article_words | set(corpus.lower().split())) 
            if article_words | set(corpus.lower().split()) else 1.0
            for corpus in corpus_texts
        )
        differentiated = min_distance < 0.3
    else:
        differentiated = True  # no corpus to compare against
    
    results.append({
        "check_name": "differentiation",
        "passed": differentiated,
        "severity": "blocking",
        "message": "Sufficiently differentiated" if differentiated else "Too similar to corpus",
    })
    
    # External citations
    ec = draft_structured_data.get("external_citations", [])
    results.append({
        "check_name": "external_citations",
        "passed": len(ec) >= 1,
        "severity": "blocking",
        "message": f"Found {len(ec)} external citation(s)" if len(ec) >= 1 else "Missing external citations",
    })
    
    # Entity density - check for proper nouns, brand names, capitalized terms
    entity_phrases = set()
    for word in text.split():
        if word and word[0].isupper() and len(word) > 2 and word.lower() not in {"the", "and", "for", "with", "this", "that", "from", "are", "can", "has", "our", "your", "best", "top"}:
            entity_phrases.add(word)
    # Also check for multi-word capitalized phrases in H1
    h1 = draft_structured_data.get("h1", "")
    if h1:
        h1_words = h1.split()
        for w in h1_words:
            if w and w[0].isupper() and len(w) > 2:
                entity_phrases.add(w)
    results.append({
        "check_name": "entity_density",
        "passed": len(entity_phrases) >= 2,
        "severity": "blocking",
        "message": f"Found {len(entity_phrases)} entities" if len(entity_phrases) >= 2 else f"Only {len(entity_phrases)} entities",
    })
    
    # Information gain (no consensus in M1, so passes no-op)
    results.append({
        "check_name": "information_gain",
        "passed": True,
        "severity": "blocking",
        "message": "No SERP consensus for this draft; information-gain requirement not applied.",
    })
    
    # Schema validation (placeholder)
    results.append({
        "check_name": "schema_validation",
        "passed": True,
        "severity": "blocking",
        "message": "Schema validation: placeholder (M1)",
    })
    
    blocked = any(not r["passed"] and r["severity"] == "blocking" for r in results)
    
    warnings = [r["message"] for r in results if not r["passed"] and r["severity"] == "advisory"]
    
    return {
        "blocked": blocked,
        "warnings": warnings,
        "results": results,
    }


def evaluate_citability(
    structured_data: dict,
) -> dict[str, Any]:
    """Evaluate draft citability (4 deterministic checks).
    
    M1: Returns score 0-100 with 4 checks. Real pseo-citability M2+.
    """
    # Find lead answer - check multiple fields used by different templates
    lead_answer = (
        structured_data.get("quick_answer")
        or structured_data.get("answer")
        or structured_data.get("introduction")
        or structured_data.get("opening_thesis")
        or structured_data.get("hook")
        or ""
    )
    lead_words = len(lead_answer.split()) if lead_answer else 0
    
    # Question headings
    questions = structured_data.get("faq", [])
    question_count = len(questions) if questions else 0
    
    # External citations
    citations = structured_data.get("external_citations", [])
    citation_count = len(citations) if citations else 0
    
    # Scannable lists
    list_fields = ["key_signals", "pro_tips", "common_mistakes", "top_picks", "criteria", "products_carried", "comparison_table"]
    has_list = any(structured_data.get(f) for f in list_fields)
    
    checks = [
        {
            "name": "direct_lead_answer",
            "passed": 25 <= lead_words <= 75,
            "detail": f"lead answer is {lead_words} words (target 25-75)",
        },
        {
            "name": "question_headings",
            "passed": question_count >= 1,
            "detail": f"{question_count} question-style heading(s)",
        },
        {
            "name": "external_citations",
            "passed": citation_count >= 1,
            "detail": f"{citation_count} external citation(s)",
        },
        {
            "name": "scannable_lists",
            "passed": has_list,
            "detail": "has at least one list/table block" if has_list else "no list/table block found",
        },
    ]
    
    passed = sum(1 for c in checks if c["passed"])
    score = round(100 * passed / len(checks))
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 50 else "D"
    
    return {
        "score": score,
        "grade": grade,
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }


def gate3_result(
    guardrail_report: dict,
    citability_report: dict,
) -> Literal["PASS", "REPAIR", "REJECT"]:
    """GATE 3 final decision.
    
    M1: PASS if no blocking failures and citability >= 50.
    REPAIR if citability 30-49 or specific advisory failures.
    REJECT if any blocking failure.
    """
    blocked = guardrail_report.get("blocked", False)
    score = citability_report.get("score", 0)
    
    if blocked:
        return "REJECT"
    
    if score < 50:
        return "REPAIR"
    
    return "PASS"