-- ============================================================================
-- User Information Collection Schema for MI Chatbot
-- Database: chatbot
-- Purpose: Store user information collected during natural conversation flow
-- Progressive collection: name, email, phone, requirements
-- ============================================================================

USE chatbot;

-- ============================================================================
-- USER_INFO TABLE - Stores collected user information per session
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_info (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL UNIQUE COMMENT 'References conversation_sessions.session_id',

    -- User fields (collected progressively)
    name VARCHAR(255) DEFAULT NULL COMMENT 'User name (first priority)',
    email VARCHAR(255) DEFAULT NULL COMMENT 'User email address',
    phone VARCHAR(50) DEFAULT NULL COMMENT 'User phone number (optional)',
    requirements TEXT DEFAULT NULL COMMENT 'JSON: structured user intent/interests/needs',

    -- Progress tracking
    completion_percentage FLOAT DEFAULT 0.0 COMMENT 'Percentage of fields collected (0.0 to 1.0)',
    fields_collected TEXT DEFAULT NULL COMMENT 'JSON array: ["name", "email", "phone", "requirements"]',

    -- Collection metadata (for resistance detection and natural flow)
    name_ask_count INT DEFAULT 0 COMMENT 'Number of times we asked for name',
    email_ask_count INT DEFAULT 0 COMMENT 'Number of times we asked for email',
    phone_ask_count INT DEFAULT 0 COMMENT 'Number of times we asked for phone',
    requirements_ask_count INT DEFAULT 0 COMMENT 'Number of times we asked for requirements',

    collection_paused BOOLEAN DEFAULT FALSE COMMENT 'Temporarily pause collection (user resistance detected)',
    last_field_asked VARCHAR(50) DEFAULT NULL COMMENT 'Last field we tried to collect',
    last_ask_at TIMESTAMP NULL COMMENT 'When we last asked for information',
    pause_until_message_count INT DEFAULT NULL COMMENT 'Resume collection after N more messages',

    -- Timestamps
    first_field_at TIMESTAMP NULL COMMENT 'When first field was collected',
    completed_at TIMESTAMP NULL COMMENT 'When all priority fields collected',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Indexes for fast lookups
    INDEX idx_session_id (session_id),
    INDEX idx_email (email),
    INDEX idx_completion (completion_percentage),
    INDEX idx_created_at (created_at),

    -- Foreign key relationship
    CONSTRAINT fk_user_info_session
        FOREIGN KEY (session_id)
        REFERENCES conversation_sessions(session_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Stores user information collected through natural conversation';

-- ============================================================================
-- UPDATE conversation_sessions table to track user info
-- ============================================================================

-- Add user_info_collected column (if it doesn't exist)
SET @column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'chatbot'
    AND TABLE_NAME = 'conversation_sessions'
    AND COLUMN_NAME = 'user_info_collected'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE conversation_sessions ADD COLUMN user_info_collected BOOLEAN DEFAULT FALSE COMMENT ''Whether any user info was collected''',
    'SELECT ''Column user_info_collected already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Add user_name column (if it doesn't exist)
SET @column_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'chatbot'
    AND TABLE_NAME = 'conversation_sessions'
    AND COLUMN_NAME = 'user_name'
);

SET @sql = IF(@column_exists = 0,
    'ALTER TABLE conversation_sessions ADD COLUMN user_name VARCHAR(255) DEFAULT NULL COMMENT ''Quick access to user name''',
    'SELECT ''Column user_name already exists'' AS message'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================================
-- ANALYTICS VIEWS
-- ============================================================================

-- User Info Collection Stats
CREATE OR REPLACE VIEW user_info_stats AS
SELECT
    COUNT(*) as total_sessions_with_info,
    SUM(CASE WHEN name IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_name,
    SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_email,
    SUM(CASE WHEN phone IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_phone,
    SUM(CASE WHEN requirements IS NOT NULL THEN 1 ELSE 0 END) as sessions_with_requirements,
    AVG(completion_percentage) * 100 as avg_completion_percentage,
    SUM(CASE WHEN completion_percentage >= 0.6 THEN 1 ELSE 0 END) as sessions_60_plus_complete,
    SUM(CASE WHEN collection_paused = TRUE THEN 1 ELSE 0 END) as sessions_with_resistance,
    AVG(name_ask_count) as avg_name_asks,
    AVG(email_ask_count) as avg_email_asks,
    AVG(phone_ask_count) as avg_phone_asks
FROM user_info
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY);

-- Daily Collection Metrics
CREATE OR REPLACE VIEW daily_collection_metrics AS
SELECT
    DATE(ui.created_at) as date,
    COUNT(*) as sessions_with_collection,
    SUM(CASE WHEN ui.name IS NOT NULL THEN 1 ELSE 0 END) as name_collected,
    SUM(CASE WHEN ui.email IS NOT NULL THEN 1 ELSE 0 END) as email_collected,
    SUM(CASE WHEN ui.phone IS NOT NULL THEN 1 ELSE 0 END) as phone_collected,
    AVG(ui.completion_percentage) * 100 as avg_completion,
    SUM(CASE WHEN ui.collection_paused = TRUE THEN 1 ELSE 0 END) as resistance_count,
    COUNT(DISTINCT cs.session_id) as total_sessions,
    (COUNT(DISTINCT ui.session_id) / COUNT(DISTINCT cs.session_id)) * 100 as collection_attempt_rate
FROM user_info ui
RIGHT JOIN conversation_sessions cs ON ui.session_id = cs.session_id
WHERE cs.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY DATE(ui.created_at)
ORDER BY date DESC;

-- Field Collection Funnel
CREATE OR REPLACE VIEW collection_funnel AS
SELECT
    'Total Sessions' as stage,
    COUNT(DISTINCT cs.session_id) as count,
    100.0 as percentage
FROM conversation_sessions cs
WHERE cs.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)

UNION ALL

SELECT
    'Collection Attempted' as stage,
    COUNT(DISTINCT ui.session_id) as count,
    (COUNT(DISTINCT ui.session_id) / (SELECT COUNT(*) FROM conversation_sessions WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY))) * 100 as percentage
FROM user_info ui
WHERE ui.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)

UNION ALL

SELECT
    'Name Collected' as stage,
    COUNT(*) as count,
    (COUNT(*) / (SELECT COUNT(*) FROM conversation_sessions WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY))) * 100 as percentage
FROM user_info
WHERE name IS NOT NULL
AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)

UNION ALL

SELECT
    'Email Collected' as stage,
    COUNT(*) as count,
    (COUNT(*) / (SELECT COUNT(*) FROM conversation_sessions WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY))) * 100 as percentage
FROM user_info
WHERE email IS NOT NULL
AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)

UNION ALL

SELECT
    'Phone Collected' as stage,
    COUNT(*) as count,
    (COUNT(*) / (SELECT COUNT(*) FROM conversation_sessions WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY))) * 100 as percentage
FROM user_info
WHERE phone IS NOT NULL
AND created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY);

-- ============================================================================
-- SAMPLE QUERIES FOR ANALYSIS
-- ============================================================================

-- Get user info for a specific session
-- SELECT * FROM user_info WHERE session_id = 'your-session-id-here';

-- Get all sessions with complete info (name + email)
-- SELECT ui.*, cs.message_count, cs.started_at
-- FROM user_info ui
-- JOIN conversation_sessions cs ON ui.session_id = cs.session_id
-- WHERE ui.name IS NOT NULL AND ui.email IS NOT NULL
-- ORDER BY ui.created_at DESC;

-- Get sessions where collection was paused (resistance detected)
-- SELECT ui.session_id, ui.fields_collected, ui.collection_paused, ui.last_field_asked, cs.message_count
-- FROM user_info ui
-- JOIN conversation_sessions cs ON ui.session_id = cs.session_id
-- WHERE ui.collection_paused = TRUE
-- ORDER BY ui.updated_at DESC;

-- Collection success rate by field
-- SELECT
--     (SELECT COUNT(*) FROM user_info WHERE name IS NOT NULL) / COUNT(*) * 100 as name_rate,
--     (SELECT COUNT(*) FROM user_info WHERE email IS NOT NULL) / COUNT(*) * 100 as email_rate,
--     (SELECT COUNT(*) FROM user_info WHERE phone IS NOT NULL) / COUNT(*) * 100 as phone_rate
-- FROM user_info
-- WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY);

-- Average asks before success
-- SELECT
--     AVG(CASE WHEN name IS NOT NULL THEN name_ask_count ELSE NULL END) as avg_asks_for_name,
--     AVG(CASE WHEN email IS NOT NULL THEN email_ask_count ELSE NULL END) as avg_asks_for_email,
--     AVG(CASE WHEN phone IS NOT NULL THEN phone_ask_count ELSE NULL END) as avg_asks_for_phone
-- FROM user_info
-- WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY);

-- ============================================================================
-- MAINTENANCE
-- ============================================================================

-- Clean up orphaned user info (sessions without conversation record)
-- DELETE FROM user_info
-- WHERE session_id NOT IN (SELECT session_id FROM conversation_sessions);

-- Archive old user info (optional - run quarterly, ensure GDPR compliance)
-- CREATE TABLE IF NOT EXISTS user_info_archive LIKE user_info;
-- INSERT INTO user_info_archive SELECT * FROM user_info WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 YEAR);
-- DELETE FROM user_info WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 YEAR);
