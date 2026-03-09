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
