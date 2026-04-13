-- IntelliRAG Database Schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants (each team/department gets an isolated knowledge base)
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Documents uploaded per tenant
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(50),
    file_size_bytes BIGINT,
    minio_object_key VARCHAR(500),
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, ready, failed
    chunk_count INT DEFAULT 0,
    error_message TEXT,
    uploaded_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Query audit log
CREATE TABLE query_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    question TEXT NOT NULL,
    answer TEXT,
    sources JSONB,
    confidence_score FLOAT,
    retrieval_ms INT,
    generation_ms INT,
    total_ms INT,
    user_id VARCHAR(100),
    user_role VARCHAR(100),
    feedback VARCHAR(10),  -- thumbs_up, thumbs_down
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- API Keys per tenant
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    label VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed: default tenant
INSERT INTO tenants (name, slug, description) VALUES
    ('General', 'general', 'Default general-purpose knowledge base'),
    ('HR Team', 'hr', 'Human Resources policies and documents'),
    ('IT Support', 'it-support', 'IT SOPs and troubleshooting guides');

CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_query_logs_tenant ON query_logs(tenant_id);
CREATE INDEX idx_query_logs_created ON query_logs(created_at DESC);

-- ── Conversational Memory ──────────────────────────────────────────────────

-- Conversation sessions (one per user browser session)
CREATE TABLE IF NOT EXISTS conversations (
    id          UUID PRIMARY KEY,
    tenant_slug VARCHAR(50) NOT NULL,
    user_id     VARCHAR(100),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);

-- Individual messages within a conversation
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_tenant   ON conversations(tenant_slug);
CREATE INDEX IF NOT EXISTS idx_conversations_expires  ON conversations(expires_at);
CREATE INDEX IF NOT EXISTS idx_messages_conversation  ON messages(conversation_id, created_at DESC);
