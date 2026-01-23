"""
Feedback Service Module

Stores user feedback and conversation history for analysis.
Designed with graceful fallback - if MySQL is unavailable, logs to file.
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
    print("[Feedback] Warning: aiomysql not installed. Run: pip install aiomysql")


class FeedbackType(str, Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING = "rating"
    COMMENT = "comment"


@dataclass
class ConversationMessage:
    role: str  # 'user' or 'assistant'
    content: str
    message_id: Optional[str] = None


@dataclass
class FeedbackData:
    session_id: str
    feedback_type: FeedbackType
    rating: Optional[int] = None  # 1-5 for rating type
    comment: Optional[str] = None
    message_id: Optional[str] = None
    assistant_message: Optional[str] = None
    user_query: Optional[str] = None
    page_url: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    conversation: Optional[List[ConversationMessage]] = None


class FeedbackService:
    """
    Service for storing and retrieving user feedback with conversation context.

    Features:
    - Async MySQL storage with connection pooling
    - Fallback to JSON file logging if MySQL unavailable
    - Full conversation history storage
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
        fallback_log_path: str = "logs/feedback_fallback.json"
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
            print("[Feedback] MySQL not available - using file fallback")
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
            print(f"[Feedback] MySQL connection pool initialized")
            return True

        except Exception as e:
            print(f"[Feedback] MySQL connection failed: {e}")
            print("[Feedback] Using file fallback for feedback storage")
            self._setup_fallback_logging()
            return False

    def _setup_fallback_logging(self):
        """Setup fallback JSON file logging"""
        log_dir = os.path.dirname(self.fallback_log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

    async def store_feedback(self, feedback: FeedbackData) -> Dict[str, Any]:
        """
        Store feedback with conversation history.

        Returns:
            Dict with 'success' bool and 'feedback_id' if successful
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()

        if self._available:
            return await self._store_to_mysql(feedback)
        else:
            return self._store_to_file(feedback)

    async def _store_to_mysql(self, feedback: FeedbackData) -> Dict[str, Any]:
        """Store feedback to MySQL database"""
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Insert feedback record
                    await cur.execute("""
                        INSERT INTO feedback (
                            session_id, feedback_type, rating, comment,
                            message_id, assistant_message, user_query,
                            page_url, user_agent, ip_address
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        feedback.session_id,
                        feedback.feedback_type.value if isinstance(feedback.feedback_type, FeedbackType) else feedback.feedback_type,
                        feedback.rating,
                        feedback.comment,
                        feedback.message_id,
                        feedback.assistant_message,
                        feedback.user_query,
                        feedback.page_url,
                        feedback.user_agent,
                        feedback.ip_address
                    ))

                    feedback_id = cur.lastrowid

                    # Insert conversation history if provided
                    if feedback.conversation:
                        for i, msg in enumerate(feedback.conversation):
                            msg_dict = msg if isinstance(msg, dict) else asdict(msg) if hasattr(msg, '__dataclass_fields__') else {'role': msg.role, 'content': msg.content}
                            await cur.execute("""
                                INSERT INTO feedback_conversations (
                                    feedback_id, role, content, message_order, message_id
                                ) VALUES (%s, %s, %s, %s, %s)
                            """, (
                                feedback_id,
                                msg_dict.get('role', 'user'),
                                msg_dict.get('content', ''),
                                i,
                                msg_dict.get('message_id')
                            ))

                    print(f"[Feedback] Stored feedback #{feedback_id} ({feedback.feedback_type})")
                    return {
                        "success": True,
                        "feedback_id": feedback_id,
                        "storage": "mysql"
                    }

        except Exception as e:
            print(f"[Feedback] MySQL storage error: {e}")
            # Fallback to file
            return self._store_to_file(feedback)

    def _store_to_file(self, feedback: FeedbackData) -> Dict[str, Any]:
        """Fallback: Store feedback to JSON file"""
        try:
            # Convert to dict
            data = {
                "timestamp": datetime.now().isoformat(),
                "session_id": feedback.session_id,
                "feedback_type": feedback.feedback_type.value if isinstance(feedback.feedback_type, FeedbackType) else feedback.feedback_type,
                "rating": feedback.rating,
                "comment": feedback.comment,
                "message_id": feedback.message_id,
                "assistant_message": feedback.assistant_message,
                "user_query": feedback.user_query,
                "page_url": feedback.page_url,
                "user_agent": feedback.user_agent,
                "ip_address": feedback.ip_address,
                "conversation": [
                    (msg if isinstance(msg, dict) else {"role": msg.role, "content": msg.content})
                    for msg in (feedback.conversation or [])
                ]
            }

            # Append to JSON file (one JSON object per line)
            with open(self.fallback_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

            print(f"[Feedback] Stored feedback to file ({feedback.feedback_type})")
            return {
                "success": True,
                "feedback_id": None,
                "storage": "file"
            }

        except Exception as e:
            print(f"[Feedback] File storage error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_feedback_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get feedback statistics for the last N days"""
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT
                            feedback_type,
                            COUNT(*) as count,
                            AVG(CASE WHEN rating IS NOT NULL THEN rating END) as avg_rating
                        FROM feedback
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        GROUP BY feedback_type
                    """, (days,))

                    stats = await cur.fetchall()

                    # Get total count
                    await cur.execute("""
                        SELECT COUNT(*) as total
                        FROM feedback
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))

                    total = await cur.fetchone()

                    return {
                        "period_days": days,
                        "total_feedback": total['total'] if total else 0,
                        "by_type": {s['feedback_type']: s['count'] for s in stats},
                        "avg_rating": next((s['avg_rating'] for s in stats if s['feedback_type'] == 'rating'), None)
                    }

        except Exception as e:
            print(f"[Feedback] Stats error: {e}")
            return {"error": str(e)}

    async def get_negative_feedback(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent negative feedback with conversation context"""
        if not self._available:
            return []

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT
                            f.id, f.session_id, f.user_query, f.assistant_message,
                            f.comment, f.page_url, f.created_at
                        FROM feedback f
                        WHERE f.feedback_type = 'thumbs_down'
                        ORDER BY f.created_at DESC
                        LIMIT %s
                    """, (limit,))

                    feedbacks = await cur.fetchall()

                    # Get conversations for each feedback
                    for fb in feedbacks:
                        await cur.execute("""
                            SELECT role, content, message_order
                            FROM feedback_conversations
                            WHERE feedback_id = %s
                            ORDER BY message_order
                        """, (fb['id'],))
                        fb['conversation'] = await cur.fetchall()
                        # Convert datetime to string for JSON serialization
                        if fb.get('created_at'):
                            fb['created_at'] = fb['created_at'].isoformat()

                    return feedbacks

        except Exception as e:
            print(f"[Feedback] Get negative feedback error: {e}")
            return []

    async def close(self):
        """Close database connections"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            print("[Feedback] Connection pool closed")

    @property
    def is_available(self) -> bool:
        """Check if feedback service is available"""
        return self._available


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_feedback_service: Optional[FeedbackService] = None


async def get_feedback_service() -> FeedbackService:
    """Get or create feedback service singleton"""
    global _feedback_service

    if _feedback_service is None:
        from chatbot.config.settings import get_settings
        settings = get_settings()

        _feedback_service = FeedbackService(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            pool_size=settings.mysql_pool_size
        )

    return _feedback_service


async def init_feedback_service() -> Optional[FeedbackService]:
    """Initialize feedback service and return it if successful"""
    service = await get_feedback_service()
    await service.initialize()
    return service
