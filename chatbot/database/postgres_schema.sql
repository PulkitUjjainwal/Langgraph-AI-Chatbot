-- ============================================================================
-- MI Chat Bot - PostgreSQL Database Schema
--
-- Architecture: PostgreSQL + pgvector + Redis
-- - PostgreSQL: All persistent data (users, conversations, messages, embeddings, FAQ)
-- - pgvector: Dynamic content embeddings with TTL
-- - Redis: Hot cache (sessions, checkpoints, temporary data)
-- - FAISS: Static knowledge base (kept for performance)
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID generation
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector for embeddings

-- ============================================================================
-- USERS & AUTHENTICATION
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('super_admin', 'admin', 'user')),
    is_active BOOLEAN DEFAULT TRUE,
    must_change_password BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active) WHERE is_active = TRUE;

COMMENT ON TABLE users IS 'User accounts with role-based access control';
COMMENT ON COLUMN users.role IS 'User role: super_admin (full access), admin (manage users), user (read-only)';

-- Refresh tokens for JWT authentication
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(512) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP,
    user_agent TEXT,
    ip_address INET
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens(token) WHERE revoked = FALSE;
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at) WHERE revoked = FALSE;

COMMENT ON TABLE refresh_tokens IS 'JWT refresh tokens for persistent login sessions';

-- ============================================================================
-- FAQ SYSTEM (Migrated from MySQL)
-- ============================================================================

CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    page_key VARCHAR(100) UNIQUE NOT NULL,
    page_name VARCHAR(255) NOT NULL,
    url_pattern VARCHAR(500) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pages_page_key ON pages(page_key);
CREATE INDEX IF NOT EXISTS idx_pages_is_active ON pages(is_active) WHERE is_active = TRUE;

COMMENT ON TABLE pages IS 'Page definitions for FAQ system with URL pattern matching';

CREATE TABLE IF NOT EXISTS faq (
    id SERIAL PRIMARY KEY,
    page_id INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    question_type VARCHAR(50) DEFAULT 'suggested' CHECK (question_type IN ('suggested', 'faq')),
    priority INTEGER DEFAULT 0,
    keywords TEXT,
    click_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_faq_page ON faq(page_id);
CREATE INDEX IF NOT EXISTS idx_faq_type ON faq(question_type);
CREATE INDEX IF NOT EXISTS idx_faq_priority ON faq(priority DESC);
CREATE INDEX IF NOT EXISTS idx_faq_is_active ON faq(is_active) WHERE is_active = TRUE;

-- Full-text search indexes for FAQ
CREATE INDEX IF NOT EXISTS idx_faq_question_fts
    ON faq USING gin(to_tsvector('english', question));
CREATE INDEX IF NOT EXISTS idx_faq_keywords_fts
    ON faq USING gin(to_tsvector('english', COALESCE(keywords, '')));

COMMENT ON TABLE faq IS 'Frequently asked questions with page-specific filtering';
COMMENT ON COLUMN faq.question_type IS 'suggested: shown proactively, faq: search results only';

-- ============================================================================
-- CONVERSATIONS & MESSAGES (Partitioned by date)
-- ============================================================================

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) UNIQUE NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    site_id VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE
) PARTITION BY RANGE (started_at);

-- Create initial partitions (extend monthly as needed)
CREATE TABLE IF NOT EXISTS conversations_2026_03 PARTITION OF conversations
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS conversations_2026_04 PARTITION OF conversations
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS conversations_2026_05 PARTITION OF conversations
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

-- Indexes on partitioned table
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_activity ON conversations(last_activity);
CREATE INDEX IF NOT EXISTS idx_conversations_site ON conversations(site_id);

COMMENT ON TABLE conversations IS 'Conversation sessions partitioned by month for efficient querying';

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL,
    role VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) PARTITION BY RANGE (created_at);

-- Create initial partitions (extend monthly as needed)
CREATE TABLE IF NOT EXISTS messages_2026_03 PARTITION OF messages
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE TABLE IF NOT EXISTS messages_2026_04 PARTITION OF messages
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');

CREATE TABLE IF NOT EXISTS messages_2026_05 PARTITION OF messages
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

-- Indexes on partitioned table
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);

COMMENT ON TABLE messages IS 'Chat messages partitioned by month, linked to conversations';

-- ============================================================================
-- VECTOR EMBEDDINGS (pgvector for dynamic content)
-- ============================================================================

CREATE TABLE IF NOT EXISTS embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type VARCHAR(50) NOT NULL,  -- 'dynamic_url', 'user_message', 'faq', etc.
    content_id VARCHAR(255),             -- Reference to original content
    content_text TEXT NOT NULL,
    embedding vector(768),               -- Dimension: 768 for nomic-embed-text
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP                 -- TTL for cleanup (NULL = never expires)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_type ON embeddings(content_type);
CREATE INDEX IF NOT EXISTS idx_embeddings_content_id ON embeddings(content_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_expires ON embeddings(expires_at)
    WHERE expires_at IS NOT NULL;

-- Vector similarity index using HNSW (Hierarchical Navigable Small World)
-- HNSW provides better performance than IVFFlat for most use cases
-- Parameters: m=16 (max connections), ef_construction=64 (build quality)
CREATE INDEX IF NOT EXISTS idx_embeddings_vector_hnsw ON embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Alternative: IVFFlat index (uncomment if memory-constrained)
-- CREATE INDEX IF NOT EXISTS idx_embeddings_vector_ivf ON embeddings
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);

COMMENT ON TABLE embeddings IS 'Vector embeddings for dynamic content with TTL (static KB uses FAISS)';
COMMENT ON COLUMN embeddings.embedding IS 'Vector dimension: 768 (nomic-embed-text model)';
COMMENT ON COLUMN embeddings.expires_at IS 'Automatic expiration for cleanup (default: 7 days)';

-- ============================================================================
-- FEEDBACK & ANALYTICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255),
    message_id UUID,  -- Can be NULL if feedback is for entire conversation
    feedback_type VARCHAR(50) NOT NULL CHECK (feedback_type IN ('thumbs_up', 'thumbs_down', 'comment', 'rating')),
    comment TEXT,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback(message_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at);

COMMENT ON TABLE feedback IS 'User feedback on chatbot responses for quality tracking';

-- ============================================================================
-- MATERIALIZED VIEWS FOR ANALYTICS
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_stats AS
SELECT
    DATE(started_at) as date,
    site_id,
    COUNT(DISTINCT id) as total_conversations,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(EXTRACT(EPOCH FROM (last_activity - started_at))) as avg_duration_seconds
FROM conversations
GROUP BY DATE(started_at), site_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_stats
    ON mv_daily_stats(date, site_id);

COMMENT ON MATERIALIZED VIEW mv_daily_stats IS 'Daily conversation statistics (refresh hourly)';

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_faq_performance AS
SELECT
    f.id,
    f.question,
    f.page_id,
    p.page_name,
    f.click_count,
    COUNT(fb.id) as feedback_count,
    AVG(CASE WHEN fb.feedback_type = 'thumbs_up' THEN 1.0 ELSE 0.0 END) as positive_rate
FROM faq f
LEFT JOIN pages p ON f.page_id = p.id
LEFT JOIN feedback fb ON fb.metadata->>'faq_id' = f.id::text
GROUP BY f.id, f.question, f.page_id, p.page_name, f.click_count;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_faq_performance
    ON mv_faq_performance(id);

COMMENT ON MATERIALIZED VIEW mv_faq_performance IS 'FAQ performance metrics (refresh daily)';

-- ============================================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pages_updated_at
    BEFORE UPDATE ON pages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_faq_updated_at
    BEFORE UPDATE ON faq
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Clean up expired embeddings
CREATE OR REPLACE FUNCTION cleanup_expired_embeddings()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM embeddings
    WHERE expires_at < CURRENT_TIMESTAMP;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_embeddings IS 'Remove expired embeddings (run via cron job)';

-- Auto-create conversation partitions
CREATE OR REPLACE FUNCTION create_conversation_partition(partition_date DATE)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    start_date := DATE_TRUNC('month', partition_date);
    end_date := start_date + INTERVAL '1 month';
    partition_name := 'conversations_' || TO_CHAR(start_date, 'YYYY_MM');

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I PARTITION OF conversations
        FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );
END;
$$ LANGUAGE plpgsql;

-- Auto-create message partitions
CREATE OR REPLACE FUNCTION create_message_partition(partition_date DATE)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    start_date := DATE_TRUNC('month', partition_date);
    end_date := start_date + INTERVAL '1 month';
    partition_name := 'messages_' || TO_CHAR(start_date, 'YYYY_MM');

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I PARTITION OF messages
        FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_conversation_partition IS 'Create monthly partition for conversations';
COMMENT ON FUNCTION create_message_partition IS 'Create monthly partition for messages';

-- ============================================================================
-- SEED DATA
-- ============================================================================

-- Default super admin user (password: Admin@123)
-- IMPORTANT: Change password immediately after first login
INSERT INTO users (email, username, password_hash, full_name, role, must_change_password)
VALUES (
    'admin@exportgenius.in',
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5Y5myHPP9I2ZS',
    'System Administrator',
    'super_admin',
    TRUE
) ON CONFLICT (email) DO NOTHING;

-- Insert default pages (Export Genius)
INSERT INTO pages (page_key, page_name, url_pattern, is_active) VALUES
    ('home', 'Home Page', '/', TRUE),
    ('search_data', 'Search Data', '/search-data', TRUE),
    ('data_license', 'Data License', '/data-license', TRUE),
    ('logistics', 'Logistics', '/logistics', TRUE),
    ('platform', 'Platform', '/platform', TRUE),
    ('api', 'API', '/api', TRUE),
    ('shipment_records', 'Shipment Records', '/shipment-records', TRUE)
ON CONFLICT (page_key) DO NOTHING;

-- Sample FAQ entries (to be populated from MySQL migration)
-- Run migration script: python scripts/migrate_mysql_to_postgres.py

-- ============================================================================
-- DATABASE MAINTENANCE
-- ============================================================================

-- View database size
CREATE OR REPLACE VIEW v_database_size AS
SELECT
    pg_size_pretty(pg_database_size(current_database())) as total_size,
    (SELECT pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))::bigint)
     FROM pg_tables WHERE schemaname = 'public') as tables_size,
    (SELECT pg_size_pretty(SUM(pg_indexes_size(schemaname||'.'||tablename))::bigint)
     FROM pg_tables WHERE schemaname = 'public') as indexes_size;

-- View table sizes
CREATE OR REPLACE VIEW v_table_sizes AS
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) as indexes_size,
    pg_total_relation_size(schemaname||'.'||tablename) as bytes
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================================================
-- PERFORMANCE TUNING
-- ============================================================================

-- Enable parallel query execution
ALTER DATABASE chatbot SET max_parallel_workers_per_gather = 4;

-- Optimize for mixed read/write workload
ALTER DATABASE chatbot SET random_page_cost = 1.1;  -- SSD-optimized
ALTER DATABASE chatbot SET effective_cache_size = '4GB';  -- Adjust based on RAM

-- ============================================================================
-- GRANT PERMISSIONS (Optional - for restricted user)
-- ============================================================================

-- Create application user (uncomment if needed)
-- CREATE USER chatbot_app WITH PASSWORD 'secure_password_here';
-- GRANT CONNECT ON DATABASE chatbot TO chatbot_app;
-- GRANT USAGE ON SCHEMA public TO chatbot_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO chatbot_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO chatbot_app;

-- ============================================================================
-- COMPLETION MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '✅ PostgreSQL schema created successfully!';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '1. Run migration script to import FAQ data from MySQL';
    RAISE NOTICE '2. Update .env file with PostgreSQL credentials';
    RAISE NOTICE '3. Install Python dependencies: pip install -r requirements.txt';
    RAISE NOTICE '4. Start the application: uvicorn fastapi_chatbot:app --reload';
    RAISE NOTICE '';
    RAISE NOTICE 'Default admin credentials:';
    RAISE NOTICE '  Email: admin@exportgenius.in';
    RAISE NOTICE '  Password: Admin@123';
    RAISE NOTICE '  IMPORTANT: Change password immediately!';
END $$;
