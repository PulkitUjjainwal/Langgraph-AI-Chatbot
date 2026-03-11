-- ============================================================================
-- Support Interactions Schema for MI Chatbot
-- Database: chatbot
-- Purpose: Track all support option clicks and user interactions with analytics
-- Links to conversation_sessions for complete user journey tracking
-- ============================================================================

USE chatbot;

-- ============================================================================
-- SUPPORT_INTERACTIONS TABLE - Stores all support option clicks
-- ============================================================================
CREATE TABLE IF NOT EXISTS support_interactions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL COMMENT 'References conversation_sessions.session_id',

    -- Interaction details
    interaction_type ENUM(
        'mode_switch',           -- User switched between General/Company mode
        'suggested_question',    -- User clicked a suggested question chip
        'url_input',            -- User entered/submitted Export Genius URL
        'lead_capture',         -- User submitted lead capture form
        'odoo_escalation',      -- User requested Odoo CRM escalation
        'twilio_callback',      -- User requested phone callback
        'voice_chat_start',     -- User started voice chat
        'voice_chat_end',       -- User ended voice chat
        'file_upload',          -- User uploaded a file
        'export_data',          -- User exported conversation/data
        'share_conversation',   -- User shared conversation
        'clear_conversation',   -- User cleared/reset conversation
        'feedback_given',       -- User gave feedback (tracked separately but counted here)
        'copy_message',         -- User copied assistant message
        'regenerate_response',  -- User requested response regeneration
        'whatsapp_request',     -- User clicked WhatsApp button (QR or link)
        'schedule_demo',        -- User clicked schedule demo button
        'chat_with_us',         -- User clicked chat with us button
        'call_request',         -- User clicked call request button
        'question_card_click',  -- User clicked question card
        'data_type_selection',  -- User selected data type (Import/Export/Both)
        'country_input',        -- User entered country
        'product_input',        -- User entered product
        'other'                 -- Other custom interactions
    ) NOT NULL COMMENT 'Type of support interaction',

    interaction_data JSON DEFAULT NULL COMMENT 'Structured data about the interaction',
    -- Examples:
    -- mode_switch: {"from": "general", "to": "company"}
    -- suggested_question: {"question": "What is Export Genius?", "index": 0}
    -- url_input: {"url": "https://...", "company_name": "ABC Corp"}
    -- lead_capture: {"email": "user@example.com", "phone": "+1234567890", "name": "John Doe"}
    -- voice_chat_start: {"duration_seconds": 120, "quality": "good"}

    -- Context
    page_url VARCHAR(500) DEFAULT NULL COMMENT 'Page URL where interaction occurred',
    message_context TEXT DEFAULT NULL COMMENT 'Related message content if applicable',
    interaction_order INT DEFAULT NULL COMMENT 'Order of this interaction in the session',

    -- Conversion tracking
    led_to_conversion BOOLEAN DEFAULT FALSE COMMENT 'Did this lead to lead capture or sale?',
    conversion_type ENUM('lead', 'callback', 'escalation', 'none') DEFAULT 'none',

    -- Device & Browser Information (for cross-device analysis)
    device_type VARCHAR(50) DEFAULT NULL COMMENT 'Device: mobile, tablet, desktop',
    browser_name VARCHAR(100) DEFAULT NULL COMMENT 'Browser name',
    os_name VARCHAR(100) DEFAULT NULL COMMENT 'Operating system',

    -- Location (for regional support preferences)
    country VARCHAR(100) DEFAULT NULL COMMENT 'Country from IP',
    region VARCHAR(100) DEFAULT NULL COMMENT 'Region/State',
    city VARCHAR(100) DEFAULT NULL COMMENT 'City',

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When interaction occurred',

    -- Indexes for fast analytics
    INDEX idx_session_id (session_id),
    INDEX idx_interaction_type (interaction_type),
    INDEX idx_created_at (created_at),
    INDEX idx_led_to_conversion (led_to_conversion),
    INDEX idx_conversion_type (conversion_type),
    INDEX idx_device_type (device_type),
    INDEX idx_country (country),

    -- Composite indexes for common queries
    INDEX idx_session_type (session_id, interaction_type),
    INDEX idx_type_created (interaction_type, created_at),
    INDEX idx_conversion_analysis (led_to_conversion, conversion_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tracks all support option clicks and interactions for analytics';

-- ============================================================================
-- SUPPORT_INTERACTION_ANALYTICS VIEW - Daily support option usage
-- ============================================================================
CREATE OR REPLACE VIEW support_interaction_analytics AS
SELECT
    DATE(created_at) as date,
    interaction_type,
    COUNT(*) as interaction_count,
    COUNT(DISTINCT session_id) as unique_sessions,
    SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) as conversions,
    ROUND(100.0 * SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate_pct,
    COUNT(DISTINCT CASE WHEN device_type = 'mobile' THEN session_id END) as mobile_users,
    COUNT(DISTINCT CASE WHEN device_type = 'desktop' THEN session_id END) as desktop_users,
    COUNT(DISTINCT CASE WHEN device_type = 'tablet' THEN session_id END) as tablet_users
FROM support_interactions
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
GROUP BY DATE(created_at), interaction_type
ORDER BY date DESC, interaction_count DESC;

-- ============================================================================
-- POPULAR_SUPPORT_OPTIONS VIEW - Most used support options
-- ============================================================================
CREATE OR REPLACE VIEW popular_support_options AS
SELECT
    interaction_type,
    COUNT(*) as total_clicks,
    COUNT(DISTINCT session_id) as unique_users,
    SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) as total_conversions,
    ROUND(100.0 * SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate_pct,
    ROUND(AVG(interaction_order), 1) as avg_interaction_order,
    COUNT(DISTINCT country) as countries_reached
FROM support_interactions
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY interaction_type
ORDER BY total_clicks DESC;

-- ============================================================================
-- SUPPORT_CONVERSION_FUNNEL VIEW - Conversion path analysis
-- ============================================================================
CREATE OR REPLACE VIEW support_conversion_funnel AS
SELECT
    si.session_id,
    cs.started_at,
    cs.message_count,
    COUNT(DISTINCT si.interaction_type) as unique_interactions_used,
    GROUP_CONCAT(DISTINCT si.interaction_type ORDER BY si.created_at SEPARATOR ' → ') as interaction_path,
    MAX(CASE WHEN si.led_to_conversion = TRUE THEN 1 ELSE 0 END) as converted,
    MAX(si.conversion_type) as conversion_type,
    cs.device_type,
    cs.country
FROM support_interactions si
JOIN conversation_sessions cs ON si.session_id = cs.session_id
WHERE si.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY si.session_id, cs.started_at, cs.message_count, cs.device_type, cs.country
HAVING converted = 1
ORDER BY cs.started_at DESC
LIMIT 1000;

-- ============================================================================
-- DEVICE_SUPPORT_PREFERENCES VIEW - Support usage by device type
-- ============================================================================
CREATE OR REPLACE VIEW device_support_preferences AS
SELECT
    device_type,
    interaction_type,
    COUNT(*) as usage_count,
    COUNT(DISTINCT session_id) as unique_sessions,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY device_type), 2) as pct_of_device_interactions
FROM support_interactions
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
AND device_type IS NOT NULL
GROUP BY device_type, interaction_type
ORDER BY device_type, usage_count DESC;

-- ============================================================================
-- GEOGRAPHIC_SUPPORT_USAGE VIEW - Support preferences by location
-- ============================================================================
CREATE OR REPLACE VIEW geographic_support_usage AS
SELECT
    country,
    region,
    interaction_type,
    COUNT(*) as usage_count,
    COUNT(DISTINCT session_id) as unique_sessions,
    SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) as conversions
FROM support_interactions
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
AND country IS NOT NULL
GROUP BY country, region, interaction_type
ORDER BY country, usage_count DESC;

-- ============================================================================
-- SESSION_SUPPORT_SUMMARY VIEW - Support interactions per session
-- ============================================================================
CREATE OR REPLACE VIEW session_support_summary AS
SELECT
    si.session_id,
    cs.started_at,
    cs.message_count,
    COUNT(si.id) as total_interactions,
    COUNT(DISTINCT si.interaction_type) as unique_interaction_types,
    MAX(CASE WHEN si.interaction_type = 'lead_capture' THEN 1 ELSE 0 END) as captured_lead,
    MAX(CASE WHEN si.interaction_type = 'odoo_escalation' THEN 1 ELSE 0 END) as escalated_to_odoo,
    MAX(CASE WHEN si.interaction_type = 'twilio_callback' THEN 1 ELSE 0 END) as requested_callback,
    MAX(CASE WHEN si.interaction_type = 'voice_chat_start' THEN 1 ELSE 0 END) as used_voice_chat,
    MAX(CASE WHEN si.led_to_conversion = TRUE THEN 1 ELSE 0 END) as had_conversion,
    cs.device_type,
    cs.country
FROM support_interactions si
JOIN conversation_sessions cs ON si.session_id = cs.session_id
WHERE si.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY si.session_id, cs.started_at, cs.message_count, cs.device_type, cs.country
ORDER BY cs.started_at DESC;

-- ============================================================================
-- HOURLY_SUPPORT_PATTERNS VIEW - Time-based usage patterns
-- ============================================================================
CREATE OR REPLACE VIEW hourly_support_patterns AS
SELECT
    HOUR(created_at) as hour_of_day,
    DAYNAME(created_at) as day_of_week,
    interaction_type,
    COUNT(*) as interaction_count,
    COUNT(DISTINCT session_id) as unique_sessions
FROM support_interactions
WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
GROUP BY HOUR(created_at), DAYNAME(created_at), interaction_type
ORDER BY hour_of_day, day_of_week;

-- ============================================================================
-- SAMPLE QUERIES FOR ANALYSIS
-- ============================================================================

-- Get all support interactions for a specific session
-- SELECT * FROM support_interactions
-- WHERE session_id = 'your-session-id-here'
-- ORDER BY created_at ASC;

-- Most popular support options in last 7 days
-- SELECT * FROM popular_support_options;

-- Conversion funnel - which interactions lead to conversions
-- SELECT * FROM support_conversion_funnel
-- WHERE converted = 1
-- LIMIT 100;

-- Support usage trends over time
-- SELECT DATE(created_at) as date, interaction_type, COUNT(*) as count
-- FROM support_interactions
-- WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
-- GROUP BY DATE(created_at), interaction_type
-- ORDER BY date DESC, count DESC;

-- Device-specific support preferences
-- SELECT * FROM device_support_preferences
-- ORDER BY device_type, usage_count DESC;

-- Geographic analysis of support options
-- SELECT country, interaction_type, COUNT(*) as usage_count
-- FROM support_interactions
-- WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
-- GROUP BY country, interaction_type
-- ORDER BY country, usage_count DESC;

-- Sessions with multiple support interactions (high engagement)
-- SELECT session_id, COUNT(*) as interaction_count,
--        GROUP_CONCAT(DISTINCT interaction_type) as types_used
-- FROM support_interactions
-- GROUP BY session_id
-- HAVING interaction_count >= 3
-- ORDER BY interaction_count DESC;

-- Conversion rate by interaction type
-- SELECT interaction_type,
--        COUNT(*) as total,
--        SUM(CASE WHEN led_to_conversion THEN 1 ELSE 0 END) as conversions,
--        ROUND(100.0 * SUM(CASE WHEN led_to_conversion THEN 1 ELSE 0 END) / COUNT(*), 2) as conversion_rate
-- FROM support_interactions
-- WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
-- GROUP BY interaction_type
-- ORDER BY conversion_rate DESC;

-- Time-based patterns (peak hours for support usage)
-- SELECT HOUR(created_at) as hour,
--        interaction_type,
--        COUNT(*) as count
-- FROM support_interactions
-- WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
-- GROUP BY HOUR(created_at), interaction_type
-- ORDER BY hour, count DESC;

-- ============================================================================
-- MAINTENANCE & OPTIMIZATION
-- ============================================================================

-- Archive old support interactions (run monthly)
-- CREATE TABLE IF NOT EXISTS support_interactions_archive LIKE support_interactions;
-- INSERT INTO support_interactions_archive
-- SELECT * FROM support_interactions
-- WHERE created_at < DATE_SUB(NOW(), INTERVAL 6 MONTH);
-- DELETE FROM support_interactions
-- WHERE created_at < DATE_SUB(NOW(), INTERVAL 6 MONTH);

-- Clean up orphaned interactions (interactions without session record)
-- DELETE FROM support_interactions
-- WHERE session_id NOT IN (SELECT session_id FROM conversation_sessions);

-- Update conversion flags when leads are captured
-- UPDATE support_interactions si
-- SET led_to_conversion = TRUE, conversion_type = 'lead'
-- WHERE si.session_id IN (
--     SELECT DISTINCT session_id FROM conversation_sessions WHERE lead_captured = TRUE
-- );

-- ============================================================================
-- PERFORMANCE NOTES
-- ============================================================================
-- 1. The interaction_data JSON field allows flexible storage of interaction-specific details
-- 2. Composite indexes optimize common query patterns (session lookups, analytics, conversions)
-- 3. Views pre-aggregate common analytics for dashboard performance
-- 4. Regular archival keeps the table size manageable for fast queries
-- 5. Foreign key relationship ensures data integrity with conversation_sessions
