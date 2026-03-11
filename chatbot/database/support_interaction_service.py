"""
Support Interaction Service Module

Tracks all support option clicks and user interactions for analytics.
Designed with graceful fallback - if MySQL is unavailable, logs to file.
Fully integrates with conversation_sessions for complete user journey tracking.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

# MySQL connector - using aiomysql for async support
try:
    import aiomysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("[SupportInteraction] Warning: aiomysql not installed. Run: pip install aiomysql")


class SupportInteractionType(str, Enum):
    MODE_SWITCH = "mode_switch"
    SUGGESTED_QUESTION = "suggested_question"
    URL_INPUT = "url_input"
    LEAD_CAPTURE = "lead_capture"
    ODOO_ESCALATION = "odoo_escalation"
    TWILIO_CALLBACK = "twilio_callback"
    VOICE_CHAT_START = "voice_chat_start"
    VOICE_CHAT_END = "voice_chat_end"
    FILE_UPLOAD = "file_upload"
    EXPORT_DATA = "export_data"
    SHARE_CONVERSATION = "share_conversation"
    CLEAR_CONVERSATION = "clear_conversation"
    FEEDBACK_GIVEN = "feedback_given"
    COPY_MESSAGE = "copy_message"
    REGENERATE_RESPONSE = "regenerate_response"
    OTHER = "other"


class ConversionType(str, Enum):
    LEAD = "lead"
    CALLBACK = "callback"
    ESCALATION = "escalation"
    NONE = "none"


@dataclass
class SupportInteraction:
    session_id: str
    interaction_type: SupportInteractionType
    interaction_data: Optional[Dict[str, Any]] = None
    page_url: Optional[str] = None
    message_context: Optional[str] = None
    interaction_order: Optional[int] = None
    led_to_conversion: bool = False
    conversion_type: ConversionType = ConversionType.NONE
    # Device & Browser Information
    device_type: Optional[str] = None
    browser_name: Optional[str] = None
    os_name: Optional[str] = None
    # Location Information
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None


class SupportInteractionService:
    """
    Service for tracking and analyzing support option clicks and interactions.

    Features:
    - Async MySQL storage with connection pooling
    - Fallback to JSON file logging if MySQL unavailable
    - Comprehensive analytics for support option usage
    - Integration with conversation_sessions table
    - Real-time conversion tracking
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "chatbot",
        pool_size: int = 5,
        fallback_log_path: str = "logs/support_interactions_fallback.json"
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.fallback_log_path = fallback_log_path

        self._pool: Optional[aiomysql.Pool] = None
        self._initialized = False
        self._available = False

    async def initialize(self) -> bool:
        """
        Initialize database connection pool.
        Returns True if successful, False otherwise.
        """
        if self._initialized:
            return self._available

        self._initialized = True

        if not MYSQL_AVAILABLE:
            print("[SupportInteraction] MySQL not available - using file fallback")
            self._setup_fallback_logging()
            return False

        try:
            self._pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                minsize=1,
                maxsize=self.pool_size,
                autocommit=True,
                connect_timeout=5
            )

            # Test connection
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    await cur.fetchone()

            self._available = True
            print(f"[SupportInteraction] MySQL connection pool initialized")
            return True

        except Exception as e:
            print(f"[SupportInteraction] MySQL connection failed: {e}")
            print("[SupportInteraction] Using file fallback for interaction storage")
            self._setup_fallback_logging()
            return False

    def _setup_fallback_logging(self):
        """Setup fallback JSON file logging"""
        log_dir = os.path.dirname(self.fallback_log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    async def track_interaction(self, interaction: SupportInteraction) -> Dict[str, Any]:
        """
        Track a support interaction.

        Returns:
            Dict with 'success' bool and 'interaction_id' if successful
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        if self._available:
            return await self._store_to_mysql(interaction)
        else:
            return self._store_to_file(interaction)

    async def _store_to_mysql(self, interaction: SupportInteraction) -> Dict[str, Any]:
        """Store interaction to MySQL database"""
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Convert interaction_data to JSON string
                    interaction_data_json = json.dumps(interaction.interaction_data) if interaction.interaction_data else None

                    # Insert interaction record
                    await cur.execute("""
                        INSERT INTO support_interactions (
                            session_id, interaction_type, interaction_data,
                            page_url, message_context, interaction_order,
                            led_to_conversion, conversion_type,
                            device_type, browser_name, os_name,
                            country, region, city
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        interaction.session_id,
                        interaction.interaction_type.value if isinstance(interaction.interaction_type, SupportInteractionType) else interaction.interaction_type,
                        interaction_data_json,
                        interaction.page_url,
                        interaction.message_context,
                        interaction.interaction_order,
                        interaction.led_to_conversion,
                        interaction.conversion_type.value if isinstance(interaction.conversion_type, ConversionType) else interaction.conversion_type,
                        interaction.device_type,
                        interaction.browser_name,
                        interaction.os_name,
                        interaction.country,
                        interaction.region,
                        interaction.city
                    ))

                    interaction_id = cur.lastrowid

                    print(f"[SupportInteraction] Tracked interaction #{interaction_id} ({interaction.interaction_type})")
                    return {
                        "success": True,
                        "interaction_id": interaction_id,
                        "storage": "mysql"
                    }

        except Exception as e:
            print(f"[SupportInteraction] MySQL storage error: {e}")
            # Fallback to file
            return self._store_to_file(interaction)

    def _store_to_file(self, interaction: SupportInteraction) -> Dict[str, Any]:
        """Fallback: Store interaction to JSON file"""
        try:
            # Convert to dict
            data = {
                "timestamp": datetime.now().isoformat(),
                "session_id": interaction.session_id,
                "interaction_type": interaction.interaction_type.value if isinstance(interaction.interaction_type, SupportInteractionType) else interaction.interaction_type,
                "interaction_data": interaction.interaction_data,
                "page_url": interaction.page_url,
                "message_context": interaction.message_context,
                "interaction_order": interaction.interaction_order,
                "led_to_conversion": interaction.led_to_conversion,
                "conversion_type": interaction.conversion_type.value if isinstance(interaction.conversion_type, ConversionType) else interaction.conversion_type,
                "device_type": interaction.device_type,
                "browser_name": interaction.browser_name,
                "os_name": interaction.os_name,
                "country": interaction.country,
                "region": interaction.region,
                "city": interaction.city
            }

            # Append to JSON file (one JSON object per line)
            with open(self.fallback_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

            print(f"[SupportInteraction] Stored interaction to file ({interaction.interaction_type})")
            return {
                "success": True,
                "interaction_id": None,
                "storage": "file"
            }

        except Exception as e:
            print(f"[SupportInteraction] File storage error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_session_interactions(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all interactions for a specific session"""
        if not self._available:
            return []

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT *
                        FROM support_interactions
                        WHERE session_id = %s
                        ORDER BY created_at ASC
                    """, (session_id,))

                    interactions = await cur.fetchall()

                    # Parse JSON data
                    for interaction in interactions:
                        if interaction.get('interaction_data'):
                            try:
                                interaction['interaction_data'] = json.loads(interaction['interaction_data'])
                            except:
                                pass
                        # Convert datetime to string
                        if interaction.get('created_at'):
                            interaction['created_at'] = interaction['created_at'].isoformat()

                    return interactions

        except Exception as e:
            print(f"[SupportInteraction] Error fetching session interactions: {e}")
            return []

    async def get_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive support interaction analytics"""
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Overall stats
                    await cur.execute("""
                        SELECT
                            COUNT(*) as total_interactions,
                            COUNT(DISTINCT session_id) as total_unique_sessions,
                            SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) as total_conversions,
                            ROUND(100.0 * SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) / COUNT(*), 2) as overall_conversion_rate
                        FROM support_interactions
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))
                    overall_stats = await cur.fetchone()

                    # Popular options from view
                    await cur.execute("""
                        SELECT * FROM popular_support_options
                    """)
                    popular_options = await cur.fetchall()

                    # Interactions by type
                    await cur.execute("""
                        SELECT interaction_type, COUNT(*) as count
                        FROM support_interactions
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        GROUP BY interaction_type
                        ORDER BY count DESC
                    """, (days,))
                    by_type = await cur.fetchall()
                    interactions_by_type = {row['interaction_type']: row['count'] for row in by_type}

                    # Interactions by device
                    await cur.execute("""
                        SELECT device_type, COUNT(*) as count
                        FROM support_interactions
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND device_type IS NOT NULL
                        GROUP BY device_type
                        ORDER BY count DESC
                    """, (days,))
                    by_device = await cur.fetchall()
                    interactions_by_device = {row['device_type']: row['count'] for row in by_device}

                    # Top countries
                    await cur.execute("""
                        SELECT
                            country,
                            COUNT(*) as count,
                            SUM(CASE WHEN led_to_conversion = TRUE THEN 1 ELSE 0 END) as conversions
                        FROM support_interactions
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND country IS NOT NULL
                        GROUP BY country
                        ORDER BY count DESC
                        LIMIT 10
                    """, (days,))
                    interactions_by_country = await cur.fetchall()

                    # Conversions by type
                    await cur.execute("""
                        SELECT conversion_type, COUNT(*) as count
                        FROM support_interactions
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND led_to_conversion = TRUE
                        GROUP BY conversion_type
                        ORDER BY count DESC
                    """, (days,))
                    by_conversion = await cur.fetchall()
                    conversions_by_type = {row['conversion_type']: row['count'] for row in by_conversion}

                    return {
                        "period_days": days,
                        "total_interactions": overall_stats['total_interactions'],
                        "total_unique_sessions": overall_stats['total_unique_sessions'],
                        "overall_conversion_rate": float(overall_stats['overall_conversion_rate'] or 0),
                        "popular_options": popular_options,
                        "interactions_by_type": interactions_by_type,
                        "interactions_by_device": interactions_by_device,
                        "interactions_by_country": interactions_by_country,
                        "total_conversions": overall_stats['total_conversions'],
                        "conversions_by_type": conversions_by_type
                    }

        except Exception as e:
            print(f"[SupportInteraction] Error fetching analytics: {e}")
            return {"error": str(e)}

    async def get_time_series(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get time series data for support analytics charts"""
        if not self._available:
            return []

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT * FROM support_interaction_analytics
                        WHERE date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                        ORDER BY date DESC, interaction_count DESC
                    """, (days,))

                    data = await cur.fetchall()

                    # Convert dates to ISO format
                    for row in data:
                        if row.get('date'):
                            row['date'] = row['date'].isoformat()

                    return data

        except Exception as e:
            print(f"[SupportInteraction] Error fetching time series: {e}")
            return []

    async def get_device_preferences(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get support option preferences by device type"""
        if not self._available:
            return []

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT * FROM device_support_preferences
                        ORDER BY device_type, usage_count DESC
                    """)

                    return await cur.fetchall()

        except Exception as e:
            print(f"[SupportInteraction] Error fetching device preferences: {e}")
            return []

    async def get_conversion_funnel(self, days: int = 30, limit: int = 100) -> Dict[str, Any]:
        """Get conversion funnel analysis"""
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get funnel items from view
                    await cur.execute("""
                        SELECT * FROM support_conversion_funnel
                        LIMIT %s
                    """, (limit,))
                    funnel_items = await cur.fetchall()

                    # Convert dates to ISO format
                    for row in funnel_items:
                        if row.get('started_at'):
                            row['started_at'] = row['started_at'].isoformat()

                    # Calculate avg interactions to convert
                    total_converted = len(funnel_items)
                    avg_interactions = sum(row['unique_interactions_used'] for row in funnel_items) / total_converted if total_converted > 0 else 0

                    # Find most common path
                    path_counts = {}
                    for row in funnel_items:
                        path = row.get('interaction_path', '')
                        path_counts[path] = path_counts.get(path, 0) + 1

                    most_common_path = max(path_counts.items(), key=lambda x: x[1])[0] if path_counts else "N/A"

                    return {
                        "funnel_items": funnel_items,
                        "total_converted_sessions": total_converted,
                        "avg_interactions_to_convert": round(avg_interactions, 2),
                        "most_common_path": most_common_path,
                        "period_days": days
                    }

        except Exception as e:
            print(f"[SupportInteraction] Error fetching conversion funnel: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close the connection pool"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            print("[SupportInteraction] Connection pool closed")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================
"""
# Initialize service
service = SupportInteractionService(
    host="localhost",
    user="root",
    password="your_password",
    database="chatbot"
)

await service.initialize()

# Track an interaction
interaction = SupportInteraction(
    session_id="user123_xyz",
    interaction_type=SupportInteractionType.SUGGESTED_QUESTION,
    interaction_data={"question": "What is Export Genius?", "index": 0},
    page_url="https://www.exportgenius.in/",
    device_type="desktop",
    country="United States"
)

result = await service.track_interaction(interaction)

# Get analytics
analytics = await service.get_analytics(days=30)
print(f"Total interactions: {analytics['total_interactions']}")
print(f"Conversion rate: {analytics['overall_conversion_rate']}%")

# Get session interactions
session_interactions = await service.get_session_interactions("user123_xyz")

# Close when done
await service.close()
"""
