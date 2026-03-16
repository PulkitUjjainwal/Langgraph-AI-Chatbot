"""
Conversation History Service Module

Stores ALL user conversations for analytics, training, and compliance.
Independent of feedback system - captures every session automatically.

Features:
- Async MySQL storage with connection pooling
- Fallback to JSON file logging if MySQL unavailable
- Stores both session metadata and full message history
- Efficient batch inserts for messages
- Background task compatible (non-blocking)
"""

import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum

# MySQL connector - using aiomysql for async support
try:
    import aiomysql
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    print("[ConversationHistory] Warning: aiomysql not installed. Run: pip install aiomysql")


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    TIMED_OUT = "timed_out"
    ERROR = "error"


@dataclass
class ConversationMessage:
    """Represents a single message in a conversation"""
    role: str  # 'user', 'assistant', or 'system'
    content: str
    message_order: int
    message_id: Optional[str] = None
    processing_time: Optional[float] = None
    sources_used: Optional[List[str]] = None
    intent_detected: Optional[str] = None
    query_type: Optional[str] = None
    credits_used: Optional[int] = None


@dataclass
class ConversationSession:
    """Represents a complete conversation session"""
    session_id: str
    messages: List[ConversationMessage]
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    initial_url: Optional[str] = None
    page_urls: Optional[List[str]] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    has_feedback: bool = False
    lead_captured: bool = False
    session_status: SessionStatus = SessionStatus.ENDED

    # Device & Browser Information
    device_type: Optional[str] = None
    browser_name: Optional[str] = None
    browser_version: Optional[str] = None
    os_name: Optional[str] = None
    os_version: Optional[str] = None

    # Location Information
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None


class ConversationHistoryService:
    """
    Service for storing and retrieving complete conversation history.

    Features:
    - Async MySQL storage with connection pooling
    - Fallback to JSON file logging if MySQL unavailable
    - Batch message inserts for efficiency
    - Session metadata tracking
    - Analytics-ready schema
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "chatbot",
        pool_size: int = 5,
        fallback_log_path: str = "logs/conversation_history_fallback.json"
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
            print("[ConversationHistory] MySQL not available - using file fallback")
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
            print(f"[ConversationHistory] MySQL connection pool initialized")
            return True

        except Exception as e:
            print(f"[ConversationHistory] MySQL connection failed: {e}")
            print("[ConversationHistory] Using file fallback for conversation storage")
            self._setup_fallback_logging()
            return False

    def _setup_fallback_logging(self):
        """Setup fallback JSON file logging"""
        log_dir = os.path.dirname(self.fallback_log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    async def ensure_session_exists(
        self,
        session_id: str,
        initial_url: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Ensure a session record exists in conversation_sessions table.
        Creates a minimal session record if it doesn't exist.

        This is CRITICAL for user_info table foreign key constraint.

        Args:
            session_id: Session identifier
            initial_url: Initial URL (optional)
            ip_address: IP address (optional)

        Returns:
            True if session exists or was created, False on error
        """
        if not self._available:
            return False

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Use INSERT IGNORE to create session only if it doesn't exist
                    await cur.execute("""
                        INSERT IGNORE INTO conversation_sessions (
                            session_id,
                            started_at,
                            last_activity,
                            initial_url,
                            ip_address,
                            message_count,
                            user_message_count,
                            assistant_message_count,
                            session_status,
                            created_at
                        ) VALUES (%s, %s, %s, %s, %s, 0, 0, 0, 'active', CURRENT_TIMESTAMP)
                    """, (
                        session_id,
                        datetime.now(),
                        datetime.now(),
                        initial_url,
                        ip_address
                    ))

            return True

        except Exception as e:
            print(f"[ConversationHistory] ensure_session_exists error: {e}")
            return False

    async def save_conversation(self, conversation: ConversationSession) -> Dict[str, Any]:
        """
        Save complete conversation session with all messages.

        Args:
            conversation: ConversationSession object with messages

        Returns:
            Dict with 'success' bool and session info
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        if self._available:
            return await self._save_to_mysql(conversation)
        else:
            return self._save_to_file(conversation)

    async def _save_to_mysql(self, conversation: ConversationSession) -> Dict[str, Any]:
        """Save conversation to MySQL database"""
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Calculate statistics
                    user_count = sum(1 for msg in conversation.messages if msg.role == 'user')
                    assistant_count = sum(1 for msg in conversation.messages if msg.role == 'assistant')
                    total_count = user_count + assistant_count

                    # Convert page_urls list to JSON string
                    page_urls_json = json.dumps(conversation.page_urls) if conversation.page_urls else None

                    # Insert or update session record
                    await cur.execute("""
                        INSERT INTO conversation_sessions (
                            session_id, started_at, ended_at, last_activity,
                            message_count, user_message_count, assistant_message_count,
                            initial_url, page_urls, user_agent, ip_address,
                            device_type, browser_name, browser_version, os_name, os_version,
                            country, region, city, timezone, language,
                            has_feedback, lead_captured, session_status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            ended_at = VALUES(ended_at),
                            last_activity = VALUES(last_activity),
                            message_count = VALUES(message_count),
                            user_message_count = VALUES(user_message_count),
                            assistant_message_count = VALUES(assistant_message_count),
                            page_urls = VALUES(page_urls),
                            device_type = VALUES(device_type),
                            browser_name = VALUES(browser_name),
                            browser_version = VALUES(browser_version),
                            os_name = VALUES(os_name),
                            os_version = VALUES(os_version),
                            country = VALUES(country),
                            region = VALUES(region),
                            city = VALUES(city),
                            timezone = VALUES(timezone),
                            language = VALUES(language),
                            has_feedback = VALUES(has_feedback),
                            lead_captured = VALUES(lead_captured),
                            session_status = VALUES(session_status),
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        conversation.session_id,
                        conversation.started_at or datetime.now(),
                        conversation.ended_at or datetime.now(),
                        conversation.last_activity or datetime.now(),
                        total_count,
                        user_count,
                        assistant_count,
                        conversation.initial_url,
                        page_urls_json,
                        conversation.user_agent,
                        conversation.ip_address,
                        conversation.device_type,
                        conversation.browser_name,
                        conversation.browser_version,
                        conversation.os_name,
                        conversation.os_version,
                        conversation.country,
                        conversation.region,
                        conversation.city,
                        conversation.timezone,
                        conversation.language,
                        conversation.has_feedback,
                        conversation.lead_captured,
                        conversation.session_status.value if isinstance(conversation.session_status, SessionStatus) else conversation.session_status
                    ))

                    # Batch insert messages
                    if conversation.messages:
                        # First, delete existing messages for this session (to avoid duplicates on re-save)
                        await cur.execute("""
                            DELETE FROM conversation_messages
                            WHERE session_id = %s
                        """, (conversation.session_id,))

                        # Prepare batch insert
                        message_values = []
                        for msg in conversation.messages:
                            sources_json = json.dumps(msg.sources_used) if msg.sources_used else None
                            message_values.append((
                                conversation.session_id,
                                msg.role,
                                msg.content,
                                msg.message_order,
                                msg.message_id,
                                msg.processing_time,
                                sources_json,
                                msg.intent_detected,
                                msg.query_type,
                                msg.credits_used
                            ))

                        # Batch insert all messages
                        await cur.executemany("""
                            INSERT INTO conversation_messages (
                                session_id, role, content, message_order, message_id,
                                processing_time, sources_used, intent_detected,
                                query_type, credits_used
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, message_values)

                    print(f"[ConversationHistory] Saved session {conversation.session_id} with {len(conversation.messages)} messages")
                    return {
                        "success": True,
                        "session_id": conversation.session_id,
                        "message_count": len(conversation.messages),
                        "storage": "mysql"
                    }

        except Exception as e:
            print(f"[ConversationHistory] MySQL storage error: {e}")
            # Fallback to file
            return self._save_to_file(conversation)

    def _save_to_file(self, conversation: ConversationSession) -> Dict[str, Any]:
        """Fallback: Store conversation to JSON file"""
        try:
            # Convert to dict
            data = {
                "timestamp": datetime.now().isoformat(),
                "session_id": conversation.session_id,
                "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
                "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
                "last_activity": conversation.last_activity.isoformat() if conversation.last_activity else None,
                "message_count": len(conversation.messages),
                "initial_url": conversation.initial_url,
                "page_urls": conversation.page_urls,
                "user_agent": conversation.user_agent,
                "ip_address": conversation.ip_address,
                "device_type": conversation.device_type,
                "browser_name": conversation.browser_name,
                "browser_version": conversation.browser_version,
                "os_name": conversation.os_name,
                "os_version": conversation.os_version,
                "country": conversation.country,
                "region": conversation.region,
                "city": conversation.city,
                "timezone": conversation.timezone,
                "language": conversation.language,
                "has_feedback": conversation.has_feedback,
                "lead_captured": conversation.lead_captured,
                "session_status": conversation.session_status.value if isinstance(conversation.session_status, SessionStatus) else conversation.session_status,
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content,
                        "message_order": msg.message_order,
                        "message_id": msg.message_id,
                        "processing_time": msg.processing_time,
                        "sources_used": msg.sources_used,
                        "intent_detected": msg.intent_detected,
                        "query_type": msg.query_type,
                        "credits_used": msg.credits_used
                    }
                    for msg in conversation.messages
                ]
            }

            # Append to JSON file (one JSON object per line)
            with open(self.fallback_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

            print(f"[ConversationHistory] Saved session {conversation.session_id} to file ({len(conversation.messages)} messages)")
            return {
                "success": True,
                "session_id": conversation.session_id,
                "message_count": len(conversation.messages),
                "storage": "file"
            }

        except Exception as e:
            print(f"[ConversationHistory] File storage error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full session with all messages.

        Args:
            session_id: Session identifier

        Returns:
            Dict with session info and messages, or None if not found
        """
        if not self._available:
            return None

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get session metadata
                    await cur.execute("""
                        SELECT * FROM conversation_sessions
                        WHERE session_id = %s
                    """, (session_id,))

                    session = await cur.fetchone()

                    if not session:
                        return None

                    # Convert timestamps to ISO format
                    for field in ['started_at', 'ended_at', 'last_activity', 'created_at', 'updated_at']:
                        if session.get(field):
                            session[field] = session[field].isoformat()

                    # Parse page_urls JSON
                    if session.get('page_urls'):
                        try:
                            session['page_urls'] = json.loads(session['page_urls'])
                        except:
                            session['page_urls'] = []

                    # Get messages
                    await cur.execute("""
                        SELECT
                            role, content, message_order, message_id,
                            processing_time, sources_used, intent_detected,
                            query_type, credits_used, created_at
                        FROM conversation_messages
                        WHERE session_id = %s
                        ORDER BY message_order ASC
                    """, (session_id,))

                    messages = await cur.fetchall()

                    # Parse JSON fields and convert timestamps
                    for msg in messages:
                        if msg.get('sources_used'):
                            try:
                                msg['sources_used'] = json.loads(msg['sources_used'])
                            except:
                                msg['sources_used'] = []
                        if msg.get('created_at'):
                            msg['created_at'] = msg['created_at'].isoformat()

                    session['messages'] = messages

                    return session

        except Exception as e:
            print(f"[ConversationHistory] Get session error: {e}")
            return None

    async def get_session_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get session statistics for the last N days"""
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT
                            COUNT(*) as total_sessions,
                            SUM(message_count) as total_messages,
                            AVG(message_count) as avg_messages_per_session,
                            SUM(CASE WHEN has_feedback = TRUE THEN 1 ELSE 0 END) as sessions_with_feedback,
                            SUM(CASE WHEN lead_captured = TRUE THEN 1 ELSE 0 END) as sessions_with_leads,
                            AVG(TIMESTAMPDIFF(MINUTE, started_at, COALESCE(ended_at, last_activity))) as avg_duration_minutes
                        FROM conversation_sessions
                        WHERE started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))

                    stats = await cur.fetchone()

                    return {
                        "period_days": days,
                        "total_sessions": stats['total_sessions'] or 0,
                        "total_messages": stats['total_messages'] or 0,
                        "avg_messages_per_session": round(stats['avg_messages_per_session'], 2) if stats['avg_messages_per_session'] else 0,
                        "sessions_with_feedback": stats['sessions_with_feedback'] or 0,
                        "sessions_with_leads": stats['sessions_with_leads'] or 0,
                        "avg_duration_minutes": round(stats['avg_duration_minutes'], 2) if stats['avg_duration_minutes'] else 0
                    }

        except Exception as e:
            print(f"[ConversationHistory] Stats error: {e}")
            return {"error": str(e)}

    async def update_session_flags(
        self,
        session_id: str,
        has_feedback: Optional[bool] = None,
        lead_captured: Optional[bool] = None,
        session_status: Optional[SessionStatus] = None
    ) -> bool:
        """
        Update session flags (e.g., when feedback is given or lead captured).

        Args:
            session_id: Session identifier
            has_feedback: Whether feedback was provided
            lead_captured: Whether lead was captured
            session_status: Session status

        Returns:
            True if successful, False otherwise
        """
        if not self._available:
            return False

        try:
            updates = []
            params = []

            if has_feedback is not None:
                updates.append("has_feedback = %s")
                params.append(has_feedback)

            if lead_captured is not None:
                updates.append("lead_captured = %s")
                params.append(lead_captured)

            if session_status is not None:
                updates.append("session_status = %s")
                params.append(session_status.value if isinstance(session_status, SessionStatus) else session_status)

            if not updates:
                return True  # Nothing to update

            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(session_id)

            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    query = f"""
                        UPDATE conversation_sessions
                        SET {', '.join(updates)}
                        WHERE session_id = %s
                    """
                    await cur.execute(query, params)

            return True

        except Exception as e:
            print(f"[ConversationHistory] Update session flags error: {e}")
            return False

    async def get_sessions_list(
        self,
        limit: int = 20,
        offset: int = 0,
        search: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        has_feedback: Optional[bool] = None,
        lead_captured: Optional[bool] = None,
        session_status: Optional[str] = None,
        sort_by: str = "started_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        Get paginated list of conversation sessions with filters.

        Args:
            limit: Number of sessions per page
            offset: Pagination offset
            search: Search in session_id or IP address
            start_date: Filter sessions from this date
            end_date: Filter sessions until this date
            has_feedback: Filter by feedback flag
            lead_captured: Filter by lead flag
            session_status: Filter by status
            sort_by: Column to sort by
            sort_order: Sort order (asc/desc)

        Returns:
            Dict with sessions list, total count, and pagination info
        """
        if not self._available:
            return {"error": "MySQL not available", "sessions": [], "total": 0}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Build WHERE clause
                    where_conditions = []
                    params = []

                    if search:
                        where_conditions.append("(session_id LIKE %s OR ip_address LIKE %s)")
                        params.extend([f"%{search}%", f"%{search}%"])

                    if start_date:
                        where_conditions.append("started_at >= %s")
                        params.append(start_date)

                    if end_date:
                        where_conditions.append("started_at <= %s")
                        params.append(end_date)

                    if has_feedback is not None:
                        where_conditions.append("has_feedback = %s")
                        params.append(has_feedback)

                    if lead_captured is not None:
                        where_conditions.append("lead_captured = %s")
                        params.append(lead_captured)

                    if session_status:
                        where_conditions.append("session_status = %s")
                        params.append(session_status)

                    where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

                    # Get total count
                    await cur.execute(f"""
                        SELECT COUNT(*) as total
                        FROM conversation_sessions
                        WHERE {where_clause}
                    """, params)

                    total = (await cur.fetchone())['total']

                    # Get sessions with pagination
                    valid_sort_columns = ['started_at', 'ended_at', 'message_count', 'session_id']
                    sort_column = sort_by if sort_by in valid_sort_columns else 'started_at'
                    order = 'DESC' if sort_order.lower() == 'desc' else 'ASC'

                    await cur.execute(f"""
                        SELECT
                            id, session_id, started_at, ended_at, last_activity,
                            message_count, user_message_count, assistant_message_count,
                            initial_url, user_agent, ip_address,
                            device_type, browser_name, browser_version,
                            os_name, os_version, country, region, city,
                            timezone, language, has_feedback, lead_captured,
                            session_status, created_at, updated_at
                        FROM conversation_sessions
                        WHERE {where_clause}
                        ORDER BY {sort_column} {order}
                        LIMIT %s OFFSET %s
                    """, params + [limit, offset])

                    sessions = await cur.fetchall()

                    # Convert timestamps to ISO format
                    for session in sessions:
                        for field in ['started_at', 'ended_at', 'last_activity', 'created_at', 'updated_at']:
                            if session.get(field):
                                session[field] = session[field].isoformat()

                    return {
                        "sessions": sessions,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": (offset + limit) < total
                    }

        except Exception as e:
            print(f"[ConversationHistory] Get sessions list error: {e}")
            return {"error": str(e), "sessions": [], "total": 0}

    async def get_time_series_data(self, days: int = 30) -> Dict[str, Any]:
        """
        Get daily time series data for conversation analytics.

        Args:
            days: Number of days to include

        Returns:
            Dict with daily breakdown of sessions and messages
        """
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT
                            DATE(started_at) as date,
                            COUNT(*) as session_count,
                            SUM(message_count) as message_count,
                            AVG(message_count) as avg_messages,
                            SUM(CASE WHEN has_feedback = TRUE THEN 1 ELSE 0 END) as feedback_count,
                            SUM(CASE WHEN lead_captured = TRUE THEN 1 ELSE 0 END) as lead_count,
                            AVG(TIMESTAMPDIFF(MINUTE, started_at, COALESCE(ended_at, last_activity))) as avg_duration
                        FROM conversation_sessions
                        WHERE started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        GROUP BY DATE(started_at)
                        ORDER BY date ASC
                    """, (days,))

                    rows = await cur.fetchall()

                    # Convert dates to ISO format
                    for row in rows:
                        if row.get('date'):
                            row['date'] = row['date'].isoformat()
                        if row.get('avg_messages'):
                            row['avg_messages'] = round(row['avg_messages'], 2)
                        if row.get('avg_duration'):
                            row['avg_duration'] = round(row['avg_duration'], 2)

                    return {
                        "period_days": days,
                        "data": rows
                    }

        except Exception as e:
            print(f"[ConversationHistory] Time series error: {e}")
            return {"error": str(e)}

    async def get_user_engagement_metrics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get user engagement metrics.

        Args:
            days: Number of days to include

        Returns:
            Dict with engagement statistics
        """
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get engagement distribution
                    await cur.execute("""
                        SELECT
                            CASE
                                WHEN message_count <= 2 THEN 'Very Low (1-2)'
                                WHEN message_count <= 5 THEN 'Low (3-5)'
                                WHEN message_count <= 10 THEN 'Medium (6-10)'
                                WHEN message_count <= 20 THEN 'High (11-20)'
                                ELSE 'Very High (20+)'
                            END as engagement_level,
                            COUNT(*) as session_count
                        FROM conversation_sessions
                        WHERE started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        GROUP BY engagement_level
                        ORDER BY MIN(message_count)
                    """, (days,))

                    engagement_distribution = await cur.fetchall()

                    # Get device breakdown
                    await cur.execute("""
                        SELECT
                            device_type,
                            COUNT(*) as count,
                            AVG(message_count) as avg_messages
                        FROM conversation_sessions
                        WHERE started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND device_type IS NOT NULL
                        GROUP BY device_type
                        ORDER BY count DESC
                    """, (days,))

                    device_breakdown = await cur.fetchall()

                    for item in device_breakdown:
                        if item.get('avg_messages'):
                            item['avg_messages'] = round(item['avg_messages'], 2)

                    # Get browser breakdown
                    await cur.execute("""
                        SELECT
                            browser_name,
                            COUNT(*) as count
                        FROM conversation_sessions
                        WHERE started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND browser_name IS NOT NULL
                        GROUP BY browser_name
                        ORDER BY count DESC
                        LIMIT 10
                    """, (days,))

                    browser_breakdown = await cur.fetchall()

                    # Get location breakdown (top countries)
                    await cur.execute("""
                        SELECT
                            country,
                            COUNT(*) as session_count,
                            AVG(message_count) as avg_messages
                        FROM conversation_sessions
                        WHERE started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND country IS NOT NULL
                        GROUP BY country
                        ORDER BY session_count DESC
                        LIMIT 10
                    """, (days,))

                    location_breakdown = await cur.fetchall()

                    for item in location_breakdown:
                        if item.get('avg_messages'):
                            item['avg_messages'] = round(item['avg_messages'], 2)

                    return {
                        "period_days": days,
                        "engagement_distribution": engagement_distribution,
                        "device_breakdown": device_breakdown,
                        "browser_breakdown": browser_breakdown,
                        "location_breakdown": location_breakdown
                    }

        except Exception as e:
            print(f"[ConversationHistory] User engagement error: {e}")
            return {"error": str(e)}

    async def get_popular_queries(self, days: int = 30, limit: int = 10) -> Dict[str, Any]:
        """
        Get popular query types and intents.

        Args:
            days: Number of days to include
            limit: Max number of results

        Returns:
            Dict with popular queries and intents
        """
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get popular query types
                    await cur.execute("""
                        SELECT
                            query_type,
                            COUNT(*) as count,
                            AVG(processing_time) as avg_processing_time,
                            AVG(credits_used) as avg_credits
                        FROM conversation_messages cm
                        JOIN conversation_sessions cs ON cm.session_id = cs.session_id
                        WHERE cs.started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND query_type IS NOT NULL
                        AND role = 'user'
                        GROUP BY query_type
                        ORDER BY count DESC
                        LIMIT %s
                    """, (days, limit))

                    query_types = await cur.fetchall()

                    for item in query_types:
                        if item.get('avg_processing_time'):
                            item['avg_processing_time'] = round(item['avg_processing_time'], 2)
                        if item.get('avg_credits'):
                            item['avg_credits'] = round(item['avg_credits'], 2)

                    # Get popular intents
                    await cur.execute("""
                        SELECT
                            intent_detected,
                            COUNT(*) as count
                        FROM conversation_messages cm
                        JOIN conversation_sessions cs ON cm.session_id = cs.session_id
                        WHERE cs.started_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        AND intent_detected IS NOT NULL
                        AND role = 'user'
                        GROUP BY intent_detected
                        ORDER BY count DESC
                        LIMIT %s
                    """, (days, limit))

                    intents = await cur.fetchall()

                    return {
                        "period_days": days,
                        "query_types": query_types,
                        "intents": intents
                    }

        except Exception as e:
            print(f"[ConversationHistory] Popular queries error: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close database connections"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            print("[ConversationHistory] Connection pool closed")

    @property
    def is_available(self) -> bool:
        """Check if conversation history service is available"""
        return self._available


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_conversation_history_service: Optional[ConversationHistoryService] = None


async def get_conversation_history_service() -> ConversationHistoryService:
    """Get or create conversation history service singleton"""
    global _conversation_history_service

    if _conversation_history_service is None:
        from chatbot.config.settings import get_settings
        settings = get_settings()

        _conversation_history_service = ConversationHistoryService(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            pool_size=settings.mysql_pool_size
        )

    return _conversation_history_service


async def init_conversation_history_service() -> Optional[ConversationHistoryService]:
    """Initialize conversation history service and return it if successful"""
    service = await get_conversation_history_service()
    await service.initialize()
    return service
