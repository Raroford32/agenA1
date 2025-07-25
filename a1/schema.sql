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

-- Vulnerabilities table
CREATE TABLE vulnerabilities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id UUID REFERENCES contracts(id),
    vulnerability_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    confidence_score DECIMAL(3,2),
    description TEXT,
    attack_vector TEXT,
    estimated_profit_eth DECIMAL(18,6),
    details JSONB,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    grok_model VARCHAR(50) DEFAULT 'grok-4-0709'
);

-- Exploits table
CREATE TABLE exploits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vulnerability_id UUID REFERENCES vulnerabilities(id),
    contract_address VARCHAR(42) NOT NULL,
    exploit_code TEXT,
    simulation_success BOOLEAN DEFAULT FALSE,
    simulated_profit_eth DECIMAL(18,6),
    executed BOOLEAN DEFAULT FALSE,
    execution_tx_hash VARCHAR(66),
    actual_profit_eth DECIMAL(18,6),
    gas_used BIGINT,
    required_funds_eth DECIMAL(18,6),
    steps JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP
);

-- Scan results table
CREATE TABLE scan_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_address VARCHAR(42) NOT NULL,
    scan_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    vulnerabilities_found INTEGER DEFAULT 0,
    exploits_generated INTEGER DEFAULT 0,
    total_profit_potential_eth DECIMAL(18,6),
    scan_duration_seconds INTEGER,
    grok_tokens_used INTEGER,
    status VARCHAR(50),
    error_message TEXT,
    full_report JSONB
);

-- Transactions table
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exploit_id UUID REFERENCES exploits(id),
    tx_hash VARCHAR(66) UNIQUE NOT NULL,
    block_number BIGINT,
    from_address VARCHAR(42),
    to_address VARCHAR(42),
    value_wei NUMERIC(78, 0),
    gas_used BIGINT,
    gas_price_gwei DECIMAL(10,2),
    status BOOLEAN,
    input_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Vector embeddings for similarity search
CREATE TABLE contract_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id UUID REFERENCES contracts(id),
    embedding vector(1536), -- OpenAI embedding dimension
    embedding_model VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indices for performance
CREATE INDEX idx_contracts_address ON contracts(address);
CREATE INDEX idx_contracts_chain_id ON contracts(chain_id);
CREATE INDEX idx_vulnerabilities_type ON vulnerabilities(vulnerability_type);
CREATE INDEX idx_vulnerabilities_severity ON vulnerabilities(severity);
CREATE INDEX idx_exploits_contract ON exploits(contract_address);
CREATE INDEX idx_exploits_executed ON exploits(executed);
CREATE INDEX idx_scan_results_contract ON scan_results(contract_address);
CREATE INDEX idx_scan_results_timestamp ON scan_results(scan_timestamp);
CREATE INDEX idx_transactions_hash ON transactions(tx_hash);
CREATE INDEX idx_contract_embeddings_vector ON contract_embeddings USING ivfflat (embedding vector_cosine_ops);

-- Triggers for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_contracts_updated_at BEFORE UPDATE ON contracts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Views for analytics
CREATE VIEW profitable_exploits AS
SELECT 
    e.contract_address,
    v.vulnerability_type,
    v.severity,
    e.simulated_profit_eth,
    e.actual_profit_eth,
    e.executed,
    e.created_at
FROM exploits e
JOIN vulnerabilities v ON e.vulnerability_id = v.id
WHERE e.simulated_profit_eth > 0.1
ORDER BY e.simulated_profit_eth DESC;

CREATE VIEW vulnerability_statistics AS
SELECT 
    vulnerability_type,
    COUNT(*) as occurrence_count,
    AVG(confidence_score) as avg_confidence,
    AVG(estimated_profit_eth) as avg_profit_eth,
    MAX(estimated_profit_eth) as max_profit_eth
FROM vulnerabilities
GROUP BY vulnerability_type
ORDER BY occurrence_count DESC;