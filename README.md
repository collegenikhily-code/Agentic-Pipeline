# SEO/AEO/GEO Pipeline — M0

Intelligent content-production pipeline combining search opportunity discovery, competitor intelligence, research, structured generation, and multi-dimensional validation.

## Architecture Overview

```
SE Ranking Discovery
    ↓
Competitor URL Collection → Bounded Crawling
    ↓
Content Extraction → Classification
    ↓
IntelligenceRecords (provenance-preserving)
    ↓
Dify Knowledge Ingestion/Retrieval (graceful degradation)
    ↓
DeepResearchAgent (LLM-powered, uses Dify + competitor intel)
    ↓
CATALYST Orchestrator (job lifecycle, concurrency, retries)
    ↓
HyperText Template Selection → TemplateRegistry Validation
    ↓
pSEO Engine (ONLY content generator)
    ↓
Unified Gates: GATE 3 (pSEO 13 guardrails + citability) + GATE 4 (AEO/GEO) + Technical SEO (11 checks)
    ↓
Final Decision: PASS / REPAIR / REJECT
    ↓
HTML Rendering + Artifacts + Traces
    ↓
LetterTrace Monitoring (optional)
```

## Quick Start

```bash
# Install dependencies
make install

# Run unit tests (no external services required)
make test

# Run pipeline (requires OPENROUTER_API_KEY)
python scripts/run_full_pipeline.py --keyword "your keyword" --intent commercial

# Verify against cached E2E artifacts
python scripts/verify_pipeline.py
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Purpose | Required |
|----------|---------|----------|
| `OPENROUTER_API_KEY` | LLM generation via LiteLLM | Yes (for generation) |
| `DIFY_API_KEY` | Knowledge retrieval/ingestion | No (graceful fallback) |
| `DIFY_BASE_URL` | Dify API endpoint | No |
| `DIFY_DATASET_ID` | Knowledge base ID | No |
| `SE_RANKING_API_KEY` | Live keyword discovery | No (uses cached artifacts) |
| `HYPERTEXT_API_KEY` | Template selection | No (fallback mode) |
| `LETTERTRACE_API_KEY` | Pipeline monitoring | No (unverified service) |
| `LANGFUSE_PUBLIC_KEY/SECRET_KEY` | LLM tracing | No |
| `POSTGRES_*` | Database (integration tests) | No |

## Test Suite

```bash
make test              # All 394 tests (unit + integration with mocks)
make test-unit         # Unit tests only
make test-integration  # Integration tests (requires Docker PostgreSQL)
```

**Verified Results:**
- 394 tests pass (0 failures)
- Cached E2E verification: 6/6 checks PASS
- LetterTrace: 16 unit tests pass, live delivery UNVERIFIED (service unreachable)

## Key Artifacts (Preserved in Git)

- `output/e2e_proof/20261006-182128/` — 3-page E2E run (facebook-business-manager, meta-business-suite-login, sora-ai-video-generator)
- `output/e2e_proof/20261005-132103/` — E2E proof with completion_status verification
- `runs/20260917-125039/` — Primary discovery artifacts (90 observations, 44 clusters, 55 competitor pages)
- `runs/20260917-134509/`, `runs/20260917-133825/` — Additional discovery runs

## Pipeline Scripts

| Script | Purpose |
|--------|---------|
| `scripts/run_full_pipeline.py` | Full pipeline: research → generation → validation |
| `scripts/verify_pipeline.py` | Offline verification against cached E2E artifacts |
| `scripts/prove_intelligence.py` | Discovery → Intelligence → Dify ingestion proof |
| `scripts/prove_research.py` | DeepResearchAgent with real LLM call |
| `scripts/prove_catalyst_concurrent.py` | CATALYST concurrency proof |

## Validation Gates

| Gate | Checks | Blocking Behavior |
|------|--------|-------------------|
| GATE 3 (pSEO) | 13 guardrails + citability | Any blocking → REJECT |
| GATE 4 (AEO/GEO) | Answer-first, entities, schema | Any REPAIR → REPAIR |
| Technical SEO | 11 deterministic HTML checks | Only blocking failures → REJECT; advisory warnings don't force REPAIR |
| Research Completeness | Questions answered, sources collected | Any partial status → REJECT |

**Decision Precedence:** REJECT > REPAIR > PASS

## Monitoring

- **LiteLLM Tracing** (built-in): Correlated traces with run_id, job_id, stage
- **Langfuse** (optional): Sink registered via `register_langfuse_sink()`
- **LetterTrace** (optional): Sink registered via `register_lettertrace_sink()` — **implementation complete, live delivery UNVERIFIED** (service unreachable, no PyPI package)

## Known Limitations

1. **Live Discovery**: Requires `SE_RANKING_API_KEY` (uses cached artifacts otherwise)
2. **Dify Retrieval**: Quota limited (HTTP 403 after ~10 documents)
3. **HyperText**: Fallback only (`HYPERTEXT_API_KEY` not configured)
4. **LetterTrace**: Service unreachable (`api.lettertrace.ai`), no PyPI package
5. **Research Quality**: Free OpenRouter model deprecated; using paid `inclusionai/ling-3.0-flash-sante`
6. **PostgreSQL**: Only needed for integration tests (Docker)

## Project Structure

```
src/seo_aeo_geo_pipeline/
├── catalyst/          # Job orchestration (CATALYST)
├── competitor/        # Crawling, extraction, intelligence mapping
├── discovery/         # SE Ranking client, clustering, opportunities
├── gates/             # Unified validation (pSEO, AEO/GEO, Technical SEO)
├── intelligence/      # IntelligenceRecords, Dify ingestion, mapping
├── observability/     # LLM tracing, Langfuse sink, LetterTrace sink
├── research/          # DeepResearchAgent, Dify RAG
├── template_layer/    # TemplateRegistry, HyperText selector
└── adapters/          # pSEO Engine adapter
```

## License

Apache-2.0