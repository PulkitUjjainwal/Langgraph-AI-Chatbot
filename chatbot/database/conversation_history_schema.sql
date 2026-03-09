-- ============================================================================
-- Conversation History Schema for MI Chatbot
-- Database: chatbot
-- Purpose: Store ALL user conversation history for analytics and training
-- Independent of feedback system - captures every session
-- ============================================================================

USE chatbot;

-- ============================================================================
-- CONVERSATION_SESSIONS TABLE - Stores session metadata
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE COMMENT 'User session identifier',

    -- Session metadata
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When session was created',
    ended_at TIMESTAMP NULL COMMENT 'When session was explicitly ended/saved',
    last_activity TIMESTAMP NULL COMMENT 'Last message timestamp',

    -- Session statistics
    message_count INT DEFAULT 0 COMMENT 'Total messages in session (user + assistant)',
    user_message_count INT DEFAULT 0 COMMENT 'Number of user messages',
    assistant_message_count INT DEFAULT 0 COMMENT 'Number of assistant messages',

    -- Context information
    initial_url VARCHAR(500) DEFAULT NULL COMMENT 'Initial page URL where chat started',
    page_urls TEXT DEFAULT NULL COMMENT 'JSON array of all pages visited during session',

    -- User information (if available)
    user_agent VARCHAR(500) DEFAULT NULL COMMENT 'Browser user agent',
    ip_address VARCHAR(45) DEFAULT NULL COMMENT 'User IP (IPv4 or IPv6)',

    -- Device & Browser Information
    device_type VARCHAR(50) DEFAULT NULL COMMENT 'Device type: mobile, tablet, desktop',
    browser_name VARCHAR(100) DEFAULT NULL COMMENT 'Browser name: Chrome, Firefox, Safari, etc.',
    browser_version VARCHAR(50) DEFAULT NULL COMMENT 'Browser version',
    os_name VARCHAR(100) DEFAULT NULL COMMENT 'Operating system name',
    os_version VARCHAR(50) DEFAULT NULL COMMENT 'Operating system version',

    -- Location Information
    country VARCHAR(100) DEFAULT NULL COMMENT 'Country from IP geolocation',
    region VARCHAR(100) DEFAULT NULL COMMENT 'Region/State from IP geolocation',
    city VARCHAR(100) DEFAULT NULL COMMENT 'City from IP geolocation',
    timezone VARCHAR(50) DEFAULT NULL COMMENT 'User timezone',
    language VARCHAR(50) DEFAULT NULL COMMENT 'Browser language preference',

    -- Session outcome
    has_feedback BOOLEAN DEFAULT FALSE COMMENT 'Whether user provided feedback',
    lead_captured BOOLEAN DEFAULT FALSE COMMENT 'Whether lead information was captured',
    session_status ENUM('active', 'ended', 'timed_out', 'error') DEFAULT 'active',

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes for fast lookups
    INDEX idx_session_id (session_id),
    INDEX idx_started_at (started_at),
    INDEX idx_ended_at (ended_at),
    INDEX idx_session_status (session_status),
    INDEX idx_has_feedback (has_feedback),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stores metadata for all chat sessions';

-- ============================================================================
-- CONVERSATION_MESSAGES TABLE - Stores all conversation messages
-- ============================================================================
CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL COMMENT 'References conversation_sessions.session_id',

    -- Message details
    role ENUM('user', 'assistant', 'system') NOT NULL COMMENT 'Message sender',
    content TEXT NOT NULL COMMENT 'Message content',
    message_order INT NOT NULL COMMENT 'Order in conversation (0, 1, 2...)',

    -- Optional metadata
    message_id VARCHAR(100) DEFAULT NULL COMMENT 'Unique message ID if available',
    processing_time FLOAT DEFAULT NULL COMMENT 'Response time in seconds (for assistant messages)',
    sources_used TEXT DEFAULT NULL COMMENT 'JSON array of sources used (for assistant messages)',
    intent_detected VARCHAR(100) DEFAULT NULL COMMENT 'Detected user intent (for user messages)',

    -- Query metadata (for analytics)
    query_type VARCHAR(50) DEFAULT NULL COMMENT 'Type of query (trade_data, country_data, general, etc.)',
    credits_used INT DEFAULT NULL COMMENT 'Credits consumed for this message',

    -- Timestamp
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key
    INDEX idx_session_id (session_id),
    INDEX idx_role (role),
    INDEX idx_message_order (message_order),
    INDEX idx_created_at (created_at),
    INDEX idx_query_type (query_type),

    -- Composite index for efficient session message retrieval
    INDEX idx_session_order (session_id, message_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stores all conversation messages for all sessions';

-- ============================================================================
-- SESSION_ANALYTICS VIEW - Quick session analytics
-- ============================================================================
CREATE OR REPLACE VIEW session_analytics AS
SELECT
    DATE(started_at) as date,
    COUNT(*) as total_sessions,
    SUM(message_count) as total_messages,
    AVG(message_count) as avg_messages_per_session,
    SUM(CASE WHEN has_feedback = TRUE THEN 1 ELSE 0 END) as sessions_with_feedback,
    SUM(CASE WHEN lead_captured = TRUE THEN 1 ELSE 0 END) as sessions_with_leads,
    AVG(TIMESTAMPDIFF(MINUTE, started_at, COALESCE(ended_at, last_activity))) as avg_session_duration_minutes
FROM conversation_sessions
WHERE started_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(started_at)
ORDER BY date DESC;

-- ============================================================================
-- POPULAR_QUERIES VIEW - Most common user queries
-- ============================================================================
CREATE OR REPLACE VIEW popular_queries AS
SELECT
    query_type,
    COUNT(*) as query_count,
    COUNT(DISTINCT session_id) as unique_sessions,
    AVG(processing_time) as avg_processing_time,
    AVG(credits_used) as avg_credits_used
FROM conversation_messages
WHERE role = 'user'
AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
AND query_type IS NOT NULL
GROUP BY query_type
ORDER BY query_count DESC;

-- ============================================================================
-- LONG_SESSIONS VIEW - Sessions with many messages (for analysis)
-- ============================================================================
CREATE OR REPLACE VIEW long_sessions AS
SELECT
    cs.session_id,
    cs.message_count,
    cs.started_at,
    cs.ended_at,
    TIMESTAMPDIFF(MINUTE, cs.started_at, COALESCE(cs.ended_at, cs.last_activity)) as duration_minutes,
    cs.has_feedback,
    cs.lead_captured
FROM conversation_sessions cs
WHERE cs.message_count >= 10
ORDER BY cs.message_count DESC, cs.started_at DESC
LIMIT 100;

-- ============================================================================
-- SAMPLE QUERIES FOR ANALYSIS
-- ============================================================================

-- Get full conversation for a session
-- SELECT cm.role, cm.content, cm.message_order, cm.created_at
-- FROM conversation_messages cm
-- WHERE cm.session_id = 'your-session-id-here'
-- ORDER BY cm.message_order ASC;

-- Get all sessions from today
-- SELECT * FROM conversation_sessions
-- WHERE DATE(started_at) = CURDATE()
-- ORDER BY started_at DESC;

-- Get sessions that didn't provide feedback
-- SELECT session_id, message_count, started_at, ended_at
-- FROM conversation_sessions
-- WHERE has_feedback = FALSE
-- AND message_count > 3
-- ORDER BY started_at DESC;

-- Daily conversation volume
-- SELECT * FROM session_analytics WHERE date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY);

-- Most popular query types
-- SELECT * FROM popular_queries;

-- Sessions with specific query types
-- SELECT DISTINCT cm.session_id, cs.started_at, cs.message_count
-- FROM conversation_messages cm
-- JOIN conversation_sessions cs ON cm.session_id = cs.session_id
-- WHERE cm.query_type = 'trade_data'
-- ORDER BY cs.started_at DESC;

-- ============================================================================
-- MAINTENANCE
-- ============================================================================

-- Archive old conversations (optional - run monthly)
-- CREATE TABLE IF NOT EXISTS conversation_messages_archive LIKE conversation_messages;
-- INSERT INTO conversation_messages_archive SELECT * FROM conversation_messages WHERE created_at < DATE_SUB(NOW(), INTERVAL 6 MONTH);
-- DELETE FROM conversation_messages WHERE created_at < DATE_SUB(NOW(), INTERVAL 6 MONTH);

-- Clean up orphaned messages (messages without session record)
-- DELETE FROM conversation_messages
-- WHERE session_id NOT IN (SELECT session_id FROM conversation_sessions);
