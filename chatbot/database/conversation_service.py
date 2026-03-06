"""
Conversation Service

Manages conversation sessions in PostgreSQL with auto-partitioning.

Features:
- Store conversation metadata
- Auto-create monthly partitions
- Track user activity
- Session analytics
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from chatbot.integrations.postgres.client import pg_client
from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


class ConversationService:
    """
    Service for managing conversations in PostgreSQL

    Features:
    - Create and track conversation sessions
    - Auto-partition by month
    - Update activity timestamps
    - Retrieve conversation history
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """Initialize service and ensure current month partition exists"""
        if self._initialized:
            return

        try:
            # Ensure this month's partition exists
            await pg_client.create_partition_if_needed('conversations', datetime.utcnow())
            self._initialized = True
            logger.info("✅ Conversation Service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Conversation Service: {e}")

    async def create_conversation(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        site_id: str = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new conversation

        Args:
            session_id: Unique session identifier
            user_id: Optional user UUID
            site_id: Site identifier (exportgenius, marketinside)
            metadata: Optional metadata (JSON)

        Returns:
            Conversation UUID

        Example:
            conversation_id = await conversation_service.create_conversation(
                session_id="session_abc123",
                site_id="exportgenius",
                metadata={"source": "web_widget", "user_agent": "Mozilla/5.0..."}
            )
        """
        if not self._initialized:
            await self.initialize()

        try:
            site = site_id or settings.site_id
            now = datetime.utcnow()

            # Ensure partition exists for current month
            await pg_client.create_partition_if_needed('conversations', now)

            # Insert conversation
            conversation_id = await pg_client.fetchval("""
                INSERT INTO conversations (
                    session_id,
                    user_id,
                    site_id,
                    started_at,
                    last_activity,
                    metadata,
                    is_active
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (session_id) DO UPDATE
                    SET last_activity = EXCLUDED.last_activity,
                        is_active = TRUE
                RETURNING id
            """,
                session_id,
                uuid.UUID(user_id) if user_id else None,
                site,
                now,
                now,
                metadata or {},
                True
            )

            logger.info(f"✅ Created conversation: {conversation_id} (session: {session_id})")
            return str(conversation_id)

        except Exception as e:
            logger.error(f"Failed to create conversation: {e}", exc_info=True)
            raise

    async def update_activity(
        self,
        session_id: str,
        metadata_update: Optional[Dict[str, Any]] = None
    ):
        """
        Update conversation last_activity timestamp

        Args:
            session_id: Session identifier
            metadata_update: Optional metadata to merge
        """
        try:
            if metadata_update:
                await pg_client.execute("""
                    UPDATE conversations
                    SET last_activity = CURRENT_TIMESTAMP,
                        metadata = metadata || $2::jsonb
                    WHERE session_id = $1
                """, session_id, metadata_update)
            else:
                await pg_client.execute("""
                    UPDATE conversations
                    SET last_activity = CURRENT_TIMESTAMP
                    WHERE session_id = $1
                """, session_id)

            logger.debug(f"Updated activity for session: {session_id}")

        except Exception as e:
            logger.error(f"Failed to update activity: {e}")

    async def get_conversation(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation by session ID

        Args:
            session_id: Session identifier

        Returns:
            Conversation dict or None
        """
        try:
            row = await pg_client.fetchrow("""
                SELECT
                    id,
                    session_id,
                    user_id,
                    site_id,
                    started_at,
                    last_activity,
                    metadata,
                    is_active
                FROM conversations
                WHERE session_id = $1
            """, session_id)

            if row:
                return {
                    'id': str(row['id']),
                    'session_id': row['session_id'],
                    'user_id': str(row['user_id']) if row['user_id'] else None,
                    'site_id': row['site_id'],
                    'started_at': row['started_at'],
                    'last_activity': row['last_activity'],
                    'metadata': row['metadata'],
                    'is_active': row['is_active']
                }
            return None

        except Exception as e:
            logger.error(f"Failed to get conversation: {e}")
            return None

    async def end_conversation(self, session_id: str):
        """
        Mark conversation as inactive

        Args:
            session_id: Session identifier
        """
        try:
            await pg_client.execute("""
                UPDATE conversations
                SET is_active = FALSE,
                    last_activity = CURRENT_TIMESTAMP
                WHERE session_id = $1
            """, session_id)

            logger.info(f"Ended conversation: {session_id}")

        except Exception as e:
            logger.error(f"Failed to end conversation: {e}")

    async def get_active_conversations(
        self,
        site_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get active conversations

        Args:
            site_id: Filter by site
            limit: Maximum results

        Returns:
            List of conversation dicts
        """
        try:
            where_clause = "WHERE is_active = TRUE"
            params = [limit]

            if site_id:
                where_clause += " AND site_id = $2"
                params.insert(0, site_id)

            sql = f"""
                SELECT
                    id,
                    session_id,
                    user_id,
                    site_id,
                    started_at,
                    last_activity,
                    metadata
                FROM conversations
                {where_clause}
                ORDER BY last_activity DESC
                LIMIT ${len(params)}
            """

            rows = await pg_client.fetch(sql, *params)

            return [{
                'id': str(row['id']),
                'session_id': row['session_id'],
                'user_id': str(row['user_id']) if row['user_id'] else None,
                'site_id': row['site_id'],
                'started_at': row['started_at'],
                'last_activity': row['last_activity'],
                'metadata': row['metadata']
            } for row in rows]

        except Exception as e:
            logger.error(f"Failed to get active conversations: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get conversation statistics

        Returns:
            Dict with stats
        """
        try:
            stats = {}

            # Total conversations
            stats['total'] = await pg_client.fetchval("""
                SELECT COUNT(*) FROM conversations
            """)

            # Active conversations
            stats['active'] = await pg_client.fetchval("""
                SELECT COUNT(*) FROM conversations WHERE is_active = TRUE
            """)

            # Today's conversations
            stats['today'] = await pg_client.fetchval("""
                SELECT COUNT(*)
                FROM conversations
                WHERE DATE(started_at) = CURRENT_DATE
            """)

            # By site
            by_site = await pg_client.fetch("""
                SELECT site_id, COUNT(*) as count
                FROM conversations
                WHERE started_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY site_id
            """)
            stats['by_site'] = {row['site_id']: row['count'] for row in by_site}

            return stats

        except Exception as e:
            logger.error(f"Failed to get conversation stats: {e}")
            return {'error': str(e)}


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_conversation_service: Optional[ConversationService] = None


async def get_conversation_service() -> ConversationService:
    """Get singleton conversation service instance"""
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
        await _conversation_service.initialize()
    return _conversation_service
