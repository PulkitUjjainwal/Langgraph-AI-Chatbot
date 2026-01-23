-- ============================================================================
-- Feedback & Conversation History Schema for MI Chatbot
-- Database: chatbot
-- Purpose: Store user feedback with full conversation context for analysis
-- ============================================================================

USE chatbot;

-- ============================================================================
-- FEEDBACK TABLE - Stores user feedback entries
-- ============================================================================
CREATE TABLE IF NOT EXISTS feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL COMMENT 'User session identifier',

    -- Feedback details
    feedback_type ENUM('thumbs_up', 'thumbs_down', 'rating', 'comment') NOT NULL,
    rating TINYINT DEFAULT NULL COMMENT '1-5 star rating (for rating type)',
    comment TEXT DEFAULT NULL COMMENT 'Optional user comment',

    -- Context
    message_id VARCHAR(100) DEFAULT NULL COMMENT 'ID of specific message being rated',
    assistant_message TEXT DEFAULT NULL COMMENT 'The assistant response that was rated',
    user_query TEXT DEFAULT NULL COMMENT 'The user question that triggered the response',

    -- Metadata
    page_url VARCHAR(500) DEFAULT NULL COMMENT 'Page URL where feedback was given',
    user_agent VARCHAR(500) DEFAULT NULL COMMENT 'Browser user agent',
    ip_address VARCHAR(45) DEFAULT NULL COMMENT 'User IP (IPv4 or IPv6)',

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for analysis queries
    INDEX idx_session_id (session_id),
    INDEX idx_feedback_type (feedback_type),
    INDEX idx_rating (rating),
    INDEX idx_created_at (created_at),
    INDEX idx_page_url (page_url(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- FEEDBACK_CONVERSATIONS TABLE - Stores conversation history with feedback
-- ============================================================================
CREATE TABLE IF NOT EXISTS feedback_conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    feedback_id INT NOT NULL COMMENT 'Foreign key to feedback table',

    -- Message details
    role ENUM('user', 'assistant', 'system') NOT NULL COMMENT 'Message sender',
    content TEXT NOT NULL COMMENT 'Message content',
    message_order INT NOT NULL COMMENT 'Order in conversation (0, 1, 2...)',

    -- Optional metadata
    message_id VARCHAR(100) DEFAULT NULL COMMENT 'Original message ID if available',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key
    FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE,

    -- Indexes
    INDEX idx_feedback_id (feedback_id),
    INDEX idx_role (role),
    INDEX idx_message_order (message_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- FEEDBACK_ANALYTICS VIEW - Quick analytics on feedback
-- ============================================================================
CREATE OR REPLACE VIEW feedback_analytics AS
SELECT
    DATE(created_at) as date,
    feedback_type,
    COUNT(*) as count,
    AVG(CASE WHEN rating IS NOT NULL THEN rating END) as avg_rating
FROM feedback
GROUP BY DATE(created_at), feedback_type
ORDER BY date DESC, feedback_type;

-- ============================================================================
-- NEGATIVE_FEEDBACK_DETAILS VIEW - For reviewing problematic responses
-- ============================================================================
CREATE OR REPLACE VIEW negative_feedback_details AS
SELECT
    f.id,
    f.session_id,
    f.user_query,
    f.assistant_message,
    f.comment,
    f.page_url,
    f.created_at,
    (SELECT COUNT(*) FROM feedback_conversations fc WHERE fc.feedback_id = f.id) as conversation_length
FROM feedback f
WHERE f.feedback_type = 'thumbs_down'
ORDER BY f.created_at DESC;

-- ============================================================================
-- SAMPLE QUERIES FOR ANALYSIS
-- ============================================================================

-- Get all negative feedback with full conversation
-- SELECT f.*, fc.role, fc.content, fc.message_order
-- FROM feedback f
-- LEFT JOIN feedback_conversations fc ON f.id = fc.feedback_id
-- WHERE f.feedback_type = 'thumbs_down'
-- ORDER BY f.created_at DESC, fc.message_order ASC;

-- Daily feedback summary
-- SELECT * FROM feedback_analytics WHERE date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY);

-- Most common pages with negative feedback
-- SELECT page_url, COUNT(*) as negative_count
-- FROM feedback
-- WHERE feedback_type = 'thumbs_down'
-- GROUP BY page_url
-- ORDER BY negative_count DESC
-- LIMIT 10;
