# Architecture Document — SEO/AEO/GEO Pipeline M0

## System Purpose

Intelligent content-production pipeline that discovers search opportunities, studies competitors, produces differentiated pages, validates them for SEO/AEO/GEO and technical quality, and monitors execution.

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SE RANKING DISCOVERY                                  │
│  • Keyword research (volume, difficulty, intent, clusters)                  │
│  • Competitor domain & ranking URL collection                               │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      COMPETITOR INTELLIGENCE                                 │
│  CompetitorCrawler: Bounded BFS, cache (TTL), robots.txt, rate limits       │
│  Extractor: Title, headings, main_content, FAQ, links, page_type            │
│  Classifier: Product, comparison, guide, FAQ, reference, other              │
│  IntelligenceMapper: SE Ranking metadata → IntelligenceRecords (provenance) │
│  CompetitorStore: File-based cache with content_hash deduplication          │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DIFY KNOWLEDGE LAYER                                 │
│  DifyRAGClient: Retrieval (graceful degradation on 403/quota)               │
│  DifyIngestionClient: Document creation with full provenance metadata       │
│  CompetitorIntel: build_research_pack(keyword) → CompetitorResearchPack     │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DEEP RESEARCH AGENT                                   │
│  DeepResearchAgent: LLM-powered (LiteLLM + OpenRouter)                      │
│  Inputs: Keyword, intent, Dify knowledge, competitor evidence               │
│  Outputs: ResearchPlan → ResearchDataset → ResearchSnapshot                 │
│  Completion Contract: complete | partial_rate_limited | partial_insufficient_*│
│  • Questions answered, evidence_by_claim, content_gaps, sources             │
│  • AEO/GEO requirements, page_type_recommendation, differentiation          │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CATALYST ORCHESTRATOR                                │
│  PageJob Lifecycle: QUEUED → RESEARCHING → RESEARCHED → COMPLETED/FAILED    │
│  Bounded Concurrency: asyncio.Semaphore / ThreadPoolExecutor               │
│  Failure Isolation: Per-job, no cross-contamination                         │
│  Retries: Bounded (default max=2), exponential backoff                      │
│  ResearchFn Adapter: Bridges CATALYST ↔ DeepResearchAgent                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HYPERTEXT TEMPLATE SELECTION                              │
│  HyperTextSelectorAdapter: Tries HyperText API → falls back to TemplateSelector│
│  Input: ResearchSnapshot (keyword, intent, page_type, AEO/GEO reqs, etc.)   │
│  Output: template_name, template_family, source (hypertext|fallback)        │
│  Registry Validation: Selected template MUST exist in TemplateRegistry      │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         pSEO ENGINE (pseo-engine-oss)                        │
│  ONLY content generator in the pipeline                                     │
│  generate_article(cluster, config) → Draft with structured_data             │
│  13 Guardrails: run_checks() → guardrail_report (9 blocking + 4 advisory)   │
│  render_article(template, structured_data) → HTML                           │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      UNIFIED VALIDATION GATES                                │
│  validate_pseo(draft, html, artifact, research_snapshot)                    │
│                                                                             │
│  GATE 3 — pSEO Integrity:                                                   │
│    • Real pSEO Engine 13-check guardrail_report (run_checks)                │
│    • Citability scoring (evaluate_citability)                               │
│    • gate3_result: blocked | REPAIR | PASS                                  │
│                                                                             │
│  GATE 4 — AEO/GEO Readiness:                                               │
│    • Citability ≥ 60, answer-first structure, clear entities, valid schema │
│    • gate4_result: REPAIR | PASS                                           │
│                                                                             │
│  Technical SEO (11 deterministic checks on rendered HTML):                  │
│    Blocking: noindex, missing title/H1, thin content, soft-404, non-2xx HTTP│
│    Advisory: canonical, meta_description, internal_links, structured_data,  │
│              indexability_readiness, http_status (pre-publish)              │
│    Advisory warnings → reported but don't force REPAIR                      │
│                                                                             │
│  Research Completeness:                                                     │
│    • complete → proceeds                                                    │
│    • partial_* → REJECT (blocking)                                          │
│                                                                             │
│  Final Decision Precedence:                                                 │
│    REJECT (any blocking) > REPAIR (gate3/gate4 REPAIR) > PASS               │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MONITORING & OBSERVABILITY                           │
│                                                                             │
│  LLMTraceCollector (in-process):                                            │
│    • ContextVars: run_id, job_id, stage                                     │
│    • LLMTraceRecord: trace_id, model, provider, latency, tokens, cost,     │
│      success/error, retry_count, metadata                                   │
│    • JSONL file persistence, in-memory buffer (1000 records)                │
│    • Extension point: register_trace_sink(callable)                         │
│                                                                             │
│  LangfuseSink (optional):                                                   │
│    • register_langfuse_sink() → Langfuse generation() events                │
│    • Requires: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, langfuse package   │
│                                                                             │
│  LetterTraceSink (optional):                                                │
│    • register_lettertrace_sink() → POST /v1/traces (Bearer auth)            │
│    • Health check: GET /health                                              │
│    • Requires: LETTERTRACE_API_KEY, LETTERTRACE_BASE_URL                    │
│    • Status: Implementation complete, live delivery UNVERIFIED             │
│      (api.lettertrace.ai unreachable, no PyPI package)                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Invariants

1. **Provenance Preservation**: Every IntelligenceRecord traces to SE Ranking keyword + competitor URL
2. **Research → Generation Coupling**: Template selection uses research_snapshot.page_type_recommendation
3. **Validation Input Integrity**: Draft carries guardrail_report from pSEO Engine; HTML rendered from same draft
4. **Decision Immutability**: REJECT/REPAIR cannot be overridden by later stages; PASS is terminal
5. **Monitoring Non-Interference**: Sink failures never affect pipeline execution or validation

## Configuration

- `config/openrouter.yaml` — Site config, generation model, brand voice
- `config/competitors.yaml` — Competitor configs (domain, seed_urls, max_pages, priority)
- Environment variables (see `.env.example`) — All external service credentials

## Artifact Contracts

### Research Snapshot (`research.json`)
```json
{
  "primary_keyword": "...",
  "intent": "commercial|informational|transactional",
  "page_type_recommendation": "comparison-guide|role-guide|product-how-to|...",
  "completion_status": "complete|partial_*",
  "sources": [...],
  "questions_answered": [...],
  "content_gaps": [...],
  "aeo_geo_requirements": [...],
  "schema_markup_needs": [...],
  "differentiation_strategy": "...",
  "audience_profile": "...",
  "source_count": N,
  "data_hash": "...",
  "provider": "deep_research_agent"
}
```

### Template Selection (`template_selection.json`)
```json
{
  "template_name": "comparison-guide",
  "template_family": "comparison",
  "confidence": 0.9,
  "source": "fallback",
  "fallback_reason": "hypertext_not_configured"
}
```

### Draft (`page.json`)
```json
{
  "slug": "...",
  "keyword": "...",
  "intent": "...",
  "template_used": "...",
  "status": "pending_review|generated",
  "structured_data": { ... },
  "meta_title": "...",
  "meta_description": "...",
  "schema_type": "...",
  "guardrail_report": { "blocked": false, "results": [...], "warnings": [...] }
}
```

### Validation (`validation.json`)
```json
{
  "decision": "PASS|REPAIR|REJECT",
  "score": 100,
  "grade": "A",
  "blocked": false,
  "warnings": [...],
  "gate3": { "blocked": false, "citability_score": 100, "guardrail_results": [...] },
  "gate4": { "citability_score": 100, "answer_first_structure": true, ... },
  "technical_seo": { "decision": "PASS", "blocked": false, "checks": {...} },
  "research_completeness": { "status": "complete", "blocked": false }
}
```

### Traces (`traces.jsonl`)
```json
{"trace_id": "...", "run_id": "...", "job_id": "...", "stage": "research|generation|validation", "operation": "...", "model": "...", "provider": "...", "latency_ms": 123.4, "success": true, "input_tokens": 100, "output_tokens": 200, "total_tokens": 300, "cost": 0.0}
```

## External Dependencies

| Service | Purpose | Required | Status |
|---------|---------|----------|--------|
| OpenRouter | LLM generation | Yes (generation) | ✅ Working (paid model) |
| SE Ranking | Keyword discovery | No (cached) | ⚠️ Needs API key |
| Dify | Knowledge RAG | No (graceful) | ⚠️ Quota limited |
| HyperText | Template selection | No (fallback) | ⚠️ No API key |
| Langfuse | LLM tracing | No | ⚠️ Not configured |
| LetterTrace | Pipeline monitoring | No | ❌ Service unreachable |
| PostgreSQL | State persistence | No (tests) | ⚠️ Docker only |

## Test Coverage

| Category | Tests | Scope |
|----------|-------|-------|
| Discovery | 67 | SE Ranking normalization, clustering, opportunities |
| Intelligence | 27 | Ingestion, mapping, retrieval, provenance |
| Research | 4 | DeepResearchAgent, completion statuses |
| Gates | 32 | pSEO, AEO/GEO, Technical SEO, unified decision |
| Catalyst | 7 | Concurrency, retries, lifecycle |
| Tracing | 11 | LLMTraceRecord, context, sinks |
| HyperText | 22 | Selection, fallback, registry validation |
| Langfuse | 17 | Sink lifecycle, auth, trace mapping |
| LetterTrace | 16 | Sink lifecycle, HTTP errors, graceful degradation |
| **Total** | **394** | **All passing** |

## Security

- No secrets in logs (API keys only in Authorization headers)
- `.env` in `.gitignore`; `.env.example` has placeholders only
- Trace records exclude prompts, full responses, API keys
- Sink failures logged at WARNING level without sensitive data

## Future Work (M1+)

1. PostgreSQL state persistence (PageJob, PageVersion, ValidationRun)
2. Live SE Ranking integration with incremental discovery
3. HyperText real API integration
4. LetterTrace service deployment & verification
5. Search-performance feedback loop (GSC integration)
6. ProductTruthDB for factual claim verification
7. Multi-page batch orchestration with dependency resolution