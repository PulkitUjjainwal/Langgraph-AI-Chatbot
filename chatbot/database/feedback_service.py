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

    # =========================================================================
    # MANAGEMENT ENDPOINTS - List, Detail, Analytics
    # =========================================================================

    async def get_feedback_list(
        self,
        page: int = 1,
        page_size: int = 20,
        feedback_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        session_id: Optional[str] = None,
        min_rating: Optional[int] = None,
        max_rating: Optional[int] = None,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        Get paginated list of feedbacks with filters.

        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            feedback_type: Filter by type (thumbs_up, thumbs_down, rating, comment)
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            session_id: Filter by session ID
            min_rating: Minimum rating filter
            max_rating: Maximum rating filter
            search: Search in user_query and assistant_message
            sort_by: Sort field (created_at, rating, feedback_type)
            sort_order: Sort order (asc, desc)

        Returns:
            Dict with feedbacks list, total count, and pagination info
        """
        if not self._available:
            return {"error": "MySQL not available", "feedbacks": [], "total": 0}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Build WHERE clause
                    conditions = []
                    params = []

                    if feedback_type:
                        conditions.append("f.feedback_type = %s")
                        params.append(feedback_type)

                    if start_date:
                        conditions.append("f.created_at >= %s")
                        params.append(f"{start_date} 00:00:00")

                    if end_date:
                        conditions.append("f.created_at <= %s")
                        params.append(f"{end_date} 23:59:59")

                    if session_id:
                        conditions.append("f.session_id = %s")
                        params.append(session_id)

                    if min_rating is not None:
                        conditions.append("f.rating >= %s")
                        params.append(min_rating)

                    if max_rating is not None:
                        conditions.append("f.rating <= %s")
                        params.append(max_rating)

                    if search:
                        conditions.append("(f.user_query LIKE %s OR f.assistant_message LIKE %s OR f.comment LIKE %s)")
                        search_param = f"%{search}%"
                        params.extend([search_param, search_param, search_param])

                    where_clause = " AND ".join(conditions) if conditions else "1=1"

                    # Validate sort_by to prevent SQL injection
                    valid_sort_fields = ["created_at", "rating", "feedback_type", "session_id"]
                    if sort_by not in valid_sort_fields:
                        sort_by = "created_at"
                    sort_order = "DESC" if sort_order.lower() == "desc" else "ASC"

                    # Get total count
                    await cur.execute(f"""
                        SELECT COUNT(*) as total FROM feedback f WHERE {where_clause}
                    """, params)
                    total_result = await cur.fetchone()
                    total = total_result['total'] if total_result else 0

                    # Calculate pagination
                    offset = (page - 1) * page_size
                    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

                    # Get feedbacks with conversation count
                    await cur.execute(f"""
                        SELECT
                            f.id, f.session_id, f.feedback_type, f.rating, f.comment,
                            f.user_query, f.assistant_message, f.page_url, f.created_at,
                            (SELECT COUNT(*) FROM feedback_conversations fc WHERE fc.feedback_id = f.id) as conversation_length
                        FROM feedback f
                        WHERE {where_clause}
                        ORDER BY f.{sort_by} {sort_order}
                        LIMIT %s OFFSET %s
                    """, params + [page_size, offset])

                    feedbacks = await cur.fetchall()

                    # Convert datetime to string
                    for fb in feedbacks:
                        if fb.get('created_at'):
                            fb['created_at'] = fb['created_at'].isoformat()

                    return {
                        "feedbacks": feedbacks,
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "total_pages": total_pages,
                        "filters_applied": {
                            "feedback_type": feedback_type,
                            "start_date": start_date,
                            "end_date": end_date,
                            "session_id": session_id,
                            "search": search
                        }
                    }

        except Exception as e:
            print(f"[Feedback] Get feedback list error: {e}")
            return {"error": str(e), "feedbacks": [], "total": 0}

    async def get_feedback_detail(self, feedback_id: int) -> Optional[Dict[str, Any]]:
        """
        Get full details of a single feedback with conversation history.

        Args:
            feedback_id: ID of the feedback

        Returns:
            Dict with full feedback details and conversation, or None if not found
        """
        if not self._available:
            return None

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get feedback
                    await cur.execute("""
                        SELECT
                            f.id, f.session_id, f.feedback_type, f.rating, f.comment,
                            f.message_id, f.user_query, f.assistant_message,
                            f.page_url, f.user_agent, f.ip_address, f.created_at
                        FROM feedback f
                        WHERE f.id = %s
                    """, (feedback_id,))

                    feedback = await cur.fetchone()

                    if not feedback:
                        return None

                    # Convert datetime
                    if feedback.get('created_at'):
                        feedback['created_at'] = feedback['created_at'].isoformat()

                    # Get conversation
                    await cur.execute("""
                        SELECT role, content, message_order, message_id
                        FROM feedback_conversations
                        WHERE feedback_id = %s
                        ORDER BY message_order
                    """, (feedback_id,))

                    feedback['conversation'] = await cur.fetchall()

                    return feedback

        except Exception as e:
            print(f"[Feedback] Get feedback detail error: {e}")
            return None

    async def get_dashboard_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Get dashboard statistics for the management UI.

        Args:
            days: Number of days to include in stats

        Returns:
            Dict with comprehensive statistics
        """
        if not self._available:
            return {"error": "MySQL not available"}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get counts by type
                    await cur.execute("""
                        SELECT
                            COUNT(*) as total,
                            SUM(CASE WHEN feedback_type = 'thumbs_up' THEN 1 ELSE 0 END) as thumbs_up_count,
                            SUM(CASE WHEN feedback_type = 'thumbs_down' THEN 1 ELSE 0 END) as thumbs_down_count,
                            SUM(CASE WHEN feedback_type = 'rating' THEN 1 ELSE 0 END) as rating_count,
                            SUM(CASE WHEN feedback_type = 'comment' THEN 1 ELSE 0 END) as comment_count,
                            AVG(CASE WHEN rating IS NOT NULL THEN rating END) as avg_rating
                        FROM feedback
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """, (days,))

                    stats = await cur.fetchone()

                    # Calculate satisfaction rate
                    thumbs_up = stats['thumbs_up_count'] or 0
                    thumbs_down = stats['thumbs_down_count'] or 0
                    satisfaction_rate = None
                    if thumbs_up + thumbs_down > 0:
                        satisfaction_rate = round((thumbs_up / (thumbs_up + thumbs_down)) * 100, 2)

                    return {
                        "total_feedback": stats['total'] or 0,
                        "thumbs_up_count": thumbs_up,
                        "thumbs_down_count": thumbs_down,
                        "rating_count": stats['rating_count'] or 0,
                        "comment_count": stats['comment_count'] or 0,
                        "avg_rating": round(stats['avg_rating'], 2) if stats['avg_rating'] else None,
                        "satisfaction_rate": satisfaction_rate,
                        "period_days": days
                    }

        except Exception as e:
            print(f"[Feedback] Get dashboard stats error: {e}")
            return {"error": str(e)}

    async def get_time_series(self, days: int = 30) -> Dict[str, Any]:
        """
        Get daily feedback data for time series charts.

        Args:
            days: Number of days to include

        Returns:
            Dict with daily statistics
        """
        if not self._available:
            return {"error": "MySQL not available", "data": []}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute("""
                        SELECT
                            DATE(created_at) as date,
                            SUM(CASE WHEN feedback_type = 'thumbs_up' THEN 1 ELSE 0 END) as thumbs_up,
                            SUM(CASE WHEN feedback_type = 'thumbs_down' THEN 1 ELSE 0 END) as thumbs_down,
                            SUM(CASE WHEN feedback_type = 'rating' THEN 1 ELSE 0 END) as rating,
                            SUM(CASE WHEN feedback_type = 'comment' THEN 1 ELSE 0 END) as comment,
                            COUNT(*) as total,
                            AVG(CASE WHEN rating IS NOT NULL THEN rating END) as avg_rating
                        FROM feedback
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        GROUP BY DATE(created_at)
                        ORDER BY date ASC
                    """, (days,))

                    results = await cur.fetchall()

                    # Convert dates to strings and round avg_rating
                    data = []
                    for row in results:
                        data.append({
                            "date": row['date'].isoformat() if row['date'] else None,
                            "thumbs_up": row['thumbs_up'] or 0,
                            "thumbs_down": row['thumbs_down'] or 0,
                            "rating": row['rating'] or 0,
                            "comment": row['comment'] or 0,
                            "total": row['total'] or 0,
                            "avg_rating": round(row['avg_rating'], 2) if row['avg_rating'] else None
                        })

                    # Calculate date range
                    from datetime import datetime, timedelta
                    end_date = datetime.now().date()
                    start_date = end_date - timedelta(days=days)

                    return {
                        "data": data,
                        "period_days": days,
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat()
                    }

        except Exception as e:
            print(f"[Feedback] Get time series error: {e}")
            return {"error": str(e), "data": []}

    async def get_top_pages(self, days: int = 30, limit: int = 10, feedback_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get top pages by feedback count.

        Args:
            days: Number of days to include
            limit: Maximum number of pages to return
            feedback_type: Optional filter by feedback type

        Returns:
            Dict with page statistics
        """
        if not self._available:
            return {"error": "MySQL not available", "pages": []}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    type_filter = ""
                    params = [days]

                    if feedback_type:
                        type_filter = "AND feedback_type = %s"
                        params.append(feedback_type)

                    params.append(limit)

                    await cur.execute(f"""
                        SELECT
                            page_url,
                            COUNT(*) as total_feedback,
                            SUM(CASE WHEN feedback_type = 'thumbs_up' THEN 1 ELSE 0 END) as thumbs_up,
                            SUM(CASE WHEN feedback_type = 'thumbs_down' THEN 1 ELSE 0 END) as thumbs_down,
                            AVG(CASE WHEN rating IS NOT NULL THEN rating END) as avg_rating
                        FROM feedback
                        WHERE created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                        {type_filter}
                        AND page_url IS NOT NULL AND page_url != ''
                        GROUP BY page_url
                        ORDER BY total_feedback DESC
                        LIMIT %s
                    """, params)

                    pages = await cur.fetchall()

                    # Round avg_rating
                    for page in pages:
                        if page.get('avg_rating'):
                            page['avg_rating'] = round(page['avg_rating'], 2)

                    return {
                        "pages": pages,
                        "period_days": days
                    }

        except Exception as e:
            print(f"[Feedback] Get top pages error: {e}")
            return {"error": str(e), "pages": []}

    async def get_session_feedbacks(self, session_id: str) -> Dict[str, Any]:
        """
        Get all feedbacks from a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Dict with all feedbacks from the session
        """
        if not self._available:
            return {"error": "MySQL not available", "feedbacks": [], "total": 0}

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # Get all feedbacks for the session
                    await cur.execute("""
                        SELECT
                            f.id, f.session_id, f.feedback_type, f.rating, f.comment,
                            f.message_id, f.user_query, f.assistant_message,
                            f.page_url, f.user_agent, f.ip_address, f.created_at
                        FROM feedback f
                        WHERE f.session_id = %s
                        ORDER BY f.created_at ASC
                    """, (session_id,))

                    feedbacks = await cur.fetchall()

                    # Get conversations for each feedback
                    for fb in feedbacks:
                        if fb.get('created_at'):
                            fb['created_at'] = fb['created_at'].isoformat()

                        await cur.execute("""
                            SELECT role, content, message_order, message_id
                            FROM feedback_conversations
                            WHERE feedback_id = %s
                            ORDER BY message_order
                        """, (fb['id'],))

                        fb['conversation'] = await cur.fetchall()

                    return {
                        "session_id": session_id,
                        "feedbacks": feedbacks,
                        "total": len(feedbacks)
                    }

        except Exception as e:
            print(f"[Feedback] Get session feedbacks error: {e}")
            return {"error": str(e), "feedbacks": [], "total": 0}

    async def export_feedbacks(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        feedback_type: Optional[str] = None,
        include_conversations: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Export feedbacks for a given period.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            feedback_type: Optional filter by type
            include_conversations: Whether to include conversation history

        Returns:
            List of feedback records
        """
        if not self._available:
            return []

        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    conditions = []
                    params = []

                    if start_date:
                        conditions.append("f.created_at >= %s")
                        params.append(f"{start_date} 00:00:00")

                    if end_date:
                        conditions.append("f.created_at <= %s")
                        params.append(f"{end_date} 23:59:59")

                    if feedback_type:
                        conditions.append("f.feedback_type = %s")
                        params.append(feedback_type)

                    where_clause = " AND ".join(conditions) if conditions else "1=1"

                    await cur.execute(f"""
                        SELECT
                            f.id, f.session_id, f.feedback_type, f.rating, f.comment,
                            f.message_id, f.user_query, f.assistant_message,
                            f.page_url, f.user_agent, f.ip_address, f.created_at
                        FROM feedback f
                        WHERE {where_clause}
                        ORDER BY f.created_at DESC
                    """, params)

                    feedbacks = await cur.fetchall()

                    for fb in feedbacks:
                        if fb.get('created_at'):
                            fb['created_at'] = fb['created_at'].isoformat()

                        if include_conversations:
                            await cur.execute("""
                                SELECT role, content, message_order
                                FROM feedback_conversations
                                WHERE feedback_id = %s
                                ORDER BY message_order
                            """, (fb['id'],))
                            fb['conversation'] = await cur.fetchall()

                    return feedbacks

        except Exception as e:
            print(f"[Feedback] Export feedbacks error: {e}")
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
