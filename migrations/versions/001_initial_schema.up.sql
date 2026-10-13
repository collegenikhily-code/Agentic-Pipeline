-- M1 Migration: Initial schema (tables created in dependency-safe order)
-- pages.current_page_version_id FK added via ALTER TABLE after page_versions exists

-- 1. pipeline_runs
CREATE TABLE pipeline_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(255) UNIQUE NOT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL,
    error_details JSONB,
    metadata JSONB
);

-- 2. opportunities
CREATE TABLE opportunities (
    id SERIAL PRIMARY KEY,
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id),
    keyword VARCHAR(500) NOT NULL,
    source VARCHAR(255),
    discovery_method VARCHAR(100),
    intent VARCHAR(50),
    business_relevance_score DECIMAL(3,2),
    information_gain boolean DEFAULT false,
    cannibalization_risk VARCHAR(20),
    duplicate_opportunity boolean DEFAULT false,
    status VARCHAR(50) NOT NULL DEFAULT 'DISCOVERED',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 3. research_snapshots
CREATE TABLE research_snapshots (
    id SERIAL PRIMARY KEY,
    opportunity_id INTEGER REFERENCES opportunities(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    source_count INTEGER DEFAULT 0,
    data_hash VARCHAR(64) NOT NULL,
    provider VARCHAR(50),
    metadata JSONB,
    UNIQUE(opportunity_id, created_at)
);

-- 4. sources
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    research_snapshot_id INTEGER REFERENCES research_snapshots(id),
    source_url TEXT NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_date DATE,
    excerpt TEXT,
    confidence DECIMAL(3,2) DEFAULT 1.0,
    verification_status VARCHAR(20) DEFAULT 'UNVERIFIED',
    collector VARCHAR(100)
);

-- 5. product_truth
CREATE TABLE product_truth (
    id SERIAL PRIMARY KEY,
    product_id VARCHAR(255),
    feature_name VARCHAR(500),
    feature_description TEXT,
    pricing_info TEXT,
    customer_type VARCHAR(100),
    statistic_source TEXT,
    confidence DECIMAL(3,2) DEFAULT 1.0,
    verification_status VARCHAR(20) DEFAULT 'PENDING',
    last_verified_at TIMESTAMP,
    source_url TEXT,
    UNIQUE(product_id, feature_name)
);

-- 6. claims
CREATE TABLE claims (
    id SERIAL PRIMARY KEY,
    product_truth_id INTEGER REFERENCES product_truth(id),
    claim_text TEXT NOT NULL,
    claim_id_uuid VARCHAR(255) UNIQUE,
    claim_type VARCHAR(50),
    confidence DECIMAL(3,2) DEFAULT 1.0,
    verification_status VARCHAR(20) DEFAULT 'PENDING',
    source_trace JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 7. evidence
CREATE TABLE evidence (
    id SERIAL PRIMARY KEY,
    claim_id INTEGER REFERENCES claims(id),
    source_id INTEGER REFERENCES sources(id),
    evidence_excerpt TEXT,
    confidence DECIMAL(3,2),
    verification_status VARCHAR(20) DEFAULT 'UNVERIFIED',
    page_location VARCHAR(500),
    product_truth_status VARCHAR(20) DEFAULT 'PENDING',
    version INTEGER DEFAULT 1
);

-- 8. page_specs
CREATE TABLE page_specs (
    id SERIAL PRIMARY KEY,
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    version INTEGER DEFAULT 1,
    page_type VARCHAR(100) NOT NULL,
    title_tag VARCHAR(600),
    meta_description VARCHAR(160),
    required_sections JSONB,
    entity_data JSONB,
    questions JSONB,
    differentiation_strategy TEXT,
    internal_linking_plan JSONB,
    schema_requirements JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    research_snapshot_id INTEGER NOT NULL REFERENCES research_snapshots(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(opportunity_id, version)
);

-- 9. pages
CREATE TABLE pages (
    id SERIAL PRIMARY KEY,
    page_spec_id INTEGER NOT NULL REFERENCES page_specs(id),
    content_path VARCHAR(500),
    generation_status VARCHAR(50) DEFAULT 'PENDING',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 10. page_versions (created AFTER pages table, FK added via ALTER TABLE later)
CREATE TABLE page_versions (
    id SERIAL PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id),
    page_spec_id INTEGER NOT NULL REFERENCES page_specs(id),
    research_snapshot_id INTEGER NOT NULL REFERENCES research_snapshots(id),
    version INTEGER NOT NULL DEFAULT 1,
    generated_content TEXT,
    generation_model VARCHAR(200),
    generation_prompt_id VARCHAR(255),
    generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    guardrail_report JSONB,
    citability_score INTEGER DEFAULT 0,
    citability_grade VARCHAR(1),
    aeo_geo_report JSONB,
    UNIQUE (page_id, version)
);

-- 11. validation_runs
CREATE TABLE validation_runs (
    id SERIAL PRIMARY KEY,
    pipeline_run_id INTEGER REFERENCES pipeline_runs(id),
    opportunity_id INTEGER REFERENCES opportunities(id),
    page_version_id INTEGER REFERENCES page_versions(id),
    page_spec_id INTEGER REFERENCES page_specs(id),
    version INTEGER DEFAULT 1,
    validation_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    pseolint_verdict VARCHAR(20),
    pseolint_categories JSONB,
    citability_score INTEGER DEFAULT 0,
    citability_grade VARCHAR(1),
    aeo_geo_report JSONB,
    overall_status VARCHAR(50)
);

-- 12. validation_findings
CREATE TABLE validation_findings (
    id SERIAL PRIMARY KEY,
    validation_run_id INTEGER REFERENCES validation_runs(id),
    finding_type VARCHAR(50) NOT NULL,
    rule_name VARCHAR(200),
    passed boolean NOT NULL,
    severity VARCHAR(20),
    message TEXT,
    remediation TEXT,
    page_version INTEGER DEFAULT 1
);

-- 13. publication_decisions
CREATE TABLE publication_decisions (
    id SERIAL PRIMARY KEY,
    validation_run_id INTEGER REFERENCES validation_runs(id),
    decision VARCHAR(20) NOT NULL,
    reason TEXT,
    repair_attempts INTEGER DEFAULT 0,
    max_repair_attempts INTEGER DEFAULT 3,
    approved_at TIMESTAMP,
    published_at TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING'
);

-- 14. measurements
CREATE TABLE measurements (
    id SERIAL PRIMARY KEY,
    publication_decision_id INTEGER REFERENCES publication_decisions(id),
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(15,4),
    metric_date DATE,
    source VARCHAR(50),
    collected_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- POST-MIGRATION: Add FK from pages to page_versions (after page_versions table exists)
-- This is executed separately via ALTER TABLE to avoid circular FK creation order issues
-- ALTER TABLE pages ADD COLUMN current_page_version_id INTEGER REFERENCES page_versions(id);