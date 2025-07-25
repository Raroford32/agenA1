-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Contracts table
CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    address VARCHAR(42) UNIQUE NOT NULL,
    chain_id INTEGER NOT NULL DEFAULT 1,
    contract_name VARCHAR(255),
    verified BOOLEAN DEFAULT FALSE,
    source_code TEXT,
    abi JSONB,
    bytecode TEXT,
    creation_tx_hash VARCHAR(66),
    creator_address VARCHAR(42),
    block_number BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern analysis results
CREATE TABLE pattern_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id UUID REFERENCES contracts(id),
    analysis_type VARCHAR(100) NOT NULL,
    patterns_found JSONB,
    innovation_score DECIMAL(5,2),
    gas_efficiency_score DECIMAL(5,2),
    code_quality_score DECIMAL(5,2),
    maintainability_score DECIMAL(5,2),
    overall_health_score DECIMAL(5,2),
    insights JSONB,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    grok_model VARCHAR(50) DEFAULT 'grok-4-0709'
);

-- Optimization opportunities
CREATE TABLE optimization_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES pattern_analyses(id),
    optimization_type VARCHAR(100) NOT NULL,
    description TEXT,
    estimated_gas_savings VARCHAR(50),
    priority VARCHAR(20),
    implementation_complexity VARCHAR(20),
    recommendations JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Architectural patterns
CREATE TABLE architectural_patterns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_id UUID REFERENCES pattern_analyses(id),
    pattern_name VARCHAR(100) NOT NULL,
    pattern_category VARCHAR(100),
    description TEXT,
    instances_found INTEGER DEFAULT 1,
    confidence_score DECIMAL(3,2),
    metadata JSONB,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Code metrics history
CREATE TABLE code_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id UUID REFERENCES contracts(id),
    metric_type VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10,2),
    metric_data JSONB,
    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pattern embeddings for similarity search
CREATE TABLE pattern_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pattern_id UUID REFERENCES architectural_patterns(id),
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analysis cache
CREATE TABLE analysis_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cache_key VARCHAR(255) UNIQUE NOT NULL,
    result JSONB,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_contracts_address ON contracts(address);
CREATE INDEX idx_contracts_chain_id ON contracts(chain_id);
CREATE INDEX idx_pattern_analyses_contract ON pattern_analyses(contract_id);
CREATE INDEX idx_pattern_analyses_type ON pattern_analyses(analysis_type);
CREATE INDEX idx_optimization_opportunities_analysis ON optimization_opportunities(analysis_id);
CREATE INDEX idx_architectural_patterns_analysis ON architectural_patterns(analysis_id);
CREATE INDEX idx_architectural_patterns_name ON architectural_patterns(pattern_name);
CREATE INDEX idx_code_metrics_contract ON code_metrics(contract_id);
CREATE INDEX idx_code_metrics_type ON code_metrics(metric_type);
CREATE INDEX idx_pattern_embeddings_vector ON pattern_embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_analysis_cache_expires ON analysis_cache(expires_at);

-- Create views for common queries
CREATE VIEW contract_health_summary AS
SELECT 
    c.address,
    c.contract_name,
    pa.innovation_score,
    pa.gas_efficiency_score,
    pa.code_quality_score,
    pa.maintainability_score,
    pa.overall_health_score,
    pa.analyzed_at,
    COUNT(DISTINCT ap.id) as unique_patterns_count,
    COUNT(DISTINCT oo.id) as optimization_opportunities_count
FROM contracts c
LEFT JOIN pattern_analyses pa ON c.id = pa.contract_id
LEFT JOIN architectural_patterns ap ON pa.id = ap.analysis_id
LEFT JOIN optimization_opportunities oo ON pa.id = oo.analysis_id
GROUP BY c.id, c.address, c.contract_name, pa.innovation_score, 
         pa.gas_efficiency_score, pa.code_quality_score, 
         pa.maintainability_score, pa.overall_health_score, pa.analyzed_at;

-- Function to clean expired cache
CREATE OR REPLACE FUNCTION clean_expired_cache() RETURNS void AS $$
BEGIN
    DELETE FROM analysis_cache WHERE expires_at < CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;