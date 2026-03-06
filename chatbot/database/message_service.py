"""
Message Service

Manages chat messages in PostgreSQL with auto-partitioning.

Features:
- Store user and assistant messages
- Auto-create monthly partitions
- Retrieve conversation history
- Message search and filtering
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


class MessageService:
    """
    Service for managing messages in PostgreSQL

    Features:
    - Store messages with role (user/assistant/system)
    - Auto-partition by month
    - Retrieve conversation history
    - Message filtering
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """Initialize service and ensure current month partition exists"""
        if self._initialized:
            return

        try:
            # Ensure this month's partition exists
            await pg_client.create_partition_if_needed('messages', datetime.utcnow())
            self._initialized = True
            logger.info("✅ Message Service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Message Service: {e}")

    async def store_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a message

        Args:
            conversation_id: Conversation UUID
            role: Message role ('user', 'assistant', 'system')
            content: Message content
            metadata: Optional metadata (sources, context, etc.)

        Returns:
            Message UUID

        Example:
            message_id = await message_service.store_message(
                conversation_id="550e8400-e29b-41d4-a716-446655440000",
                role="user",
                content="What are HS codes?",
                metadata={"ip_address": "1.2.3.4"}
            )
        """
        if not self._initialized:
            await self.initialize()

        try:
            now = datetime.utcnow()

            # Ensure partition exists for current month
            await pg_client.create_partition_if_needed('messages', now)

            # Insert message
            message_id = await pg_client.fetchval("""
                INSERT INTO messages (
                    conversation_id,
                    role,
                    content,
                    metadata,
                    created_at
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """,
                uuid.UUID(conversation_id),
                role,
                content,
                metadata or {},
                now
            )

            logger.debug(f"Stored {role} message: {str(message_id)[:8]}...")
            return str(message_id)

        except Exception as e:
            logger.error(f"Failed to store message: {e}", exc_info=True)
            raise

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get messages for a conversation

        Args:
            conversation_id: Conversation UUID
            limit: Maximum messages to return (None = all)
            offset: Number of messages to skip

        Returns:
            List of message dicts ordered by creation time

        Example:
            messages = await message_service.get_conversation_messages(
                conversation_id="550e8400...",
                limit=20
            )

            for msg in messages:
                print(f"{msg['role']}: {msg['content']}")
        """
        try:
            params = [uuid.UUID(conversation_id)]
            param_idx = 2

            limit_clause = ""
            if limit:
                limit_clause = f"LIMIT ${param_idx}"
                params.append(limit)
                param_idx += 1

                if offset:
                    limit_clause += f" OFFSET ${param_idx}"
                    params.append(offset)

            sql = f"""
                SELECT
                    id,
                    conversation_id,
                    role,
                    content,
                    metadata,
                    created_at
                FROM messages
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                {limit_clause}
            """

            rows = await pg_client.fetch(sql, *params)

            return [{
                'id': str(row['id']),
                'conversation_id': str(row['conversation_id']),
                'role': row['role'],
                'content': row['content'],
                'metadata': row['metadata'],
                'created_at': row['created_at']
            } for row in rows]

        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return []

    async def get_recent_messages(
        self,
        conversation_id: str,
        count: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get most recent messages for a conversation

        Args:
            conversation_id: Conversation UUID
            count: Number of recent messages

        Returns:
            List of message dicts (most recent last)
        """
        try:
            rows = await pg_client.fetch("""
                SELECT
                    id,
                    conversation_id,
                    role,
                    content,
                    metadata,
                    created_at
                FROM messages
                WHERE conversation_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, uuid.UUID(conversation_id), count)

            # Reverse to get chronological order (oldest first)
            messages = [{
                'id': str(row['id']),
                'conversation_id': str(row['conversation_id']),
                'role': row['role'],
                'content': row['content'],
                'metadata': row['metadata'],
                'created_at': row['created_at']
            } for row in rows]

            return list(reversed(messages))

        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []

    async def count_messages(self, conversation_id: str) -> int:
        """
        Count total messages in a conversation

        Args:
            conversation_id: Conversation UUID

        Returns:
            Message count
        """
        try:
            count = await pg_client.fetchval("""
                SELECT COUNT(*)
                FROM messages
                WHERE conversation_id = $1
            """, uuid.UUID(conversation_id))

            return count or 0

        except Exception as e:
            logger.error(f"Failed to count messages: {e}")
            return 0

    async def delete_conversation_messages(self, conversation_id: str) -> int:
        """
        Delete all messages for a conversation

        Args:
            conversation_id: Conversation UUID

        Returns:
            Number of messages deleted
        """
        try:
            result = await pg_client.execute("""
                DELETE FROM messages WHERE conversation_id = $1
            """, uuid.UUID(conversation_id))

            deleted = int(result.split()[-1])
            logger.info(f"Deleted {deleted} messages for conversation {conversation_id[:8]}...")
            return deleted

        except Exception as e:
            logger.error(f"Failed to delete messages: {e}")
            return 0

    async def search_messages(
        self,
        query: str,
        site_id: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search messages by content

        Args:
            query: Search query
            site_id: Filter by site
            role: Filter by role ('user', 'assistant')
            limit: Maximum results

        Returns:
            List of message dicts

        Example:
            messages = await message_service.search_messages(
                query="HS code",
                role="user",
                limit=10
            )
        """
        try:
            where_clauses = ["content ILIKE $1"]
            params = [f"%{query}%", limit]
            param_idx = 3

            if role:
                where_clauses.append(f"role = ${param_idx}")
                params.insert(1, role)
                param_idx += 1

            if site_id:
                where_clauses.append(f"""
                    conversation_id IN (
                        SELECT id FROM conversations WHERE site_id = ${param_idx}
                    )
                """)
                params.insert(-1, site_id)
                param_idx += 1

            where_clause = " AND ".join(where_clauses)

            sql = f"""
                SELECT
                    m.id,
                    m.conversation_id,
                    m.role,
                    m.content,
                    m.metadata,
                    m.created_at
                FROM messages m
                WHERE {where_clause}
                ORDER BY m.created_at DESC
                LIMIT ${len(params)}
            """

            rows = await pg_client.fetch(sql, *params)

            return [{
                'id': str(row['id']),
                'conversation_id': str(row['conversation_id']),
                'role': row['role'],
                'content': row['content'],
                'metadata': row['metadata'],
                'created_at': row['created_at']
            } for row in rows]

        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get message statistics

        Returns:
            Dict with stats
        """
        try:
            stats = {}

            # Total messages
            stats['total'] = await pg_client.fetchval("""
                SELECT COUNT(*) FROM messages
            """)

            # Today's messages
            stats['today'] = await pg_client.fetchval("""
                SELECT COUNT(*)
                FROM messages
                WHERE DATE(created_at) = CURRENT_DATE
            """)

            # By role
            by_role = await pg_client.fetch("""
                SELECT role, COUNT(*) as count
                FROM messages
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY role
            """)
            stats['by_role'] = {row['role']: row['count'] for row in by_role}

            # Average message length
            stats['avg_length'] = await pg_client.fetchval("""
                SELECT AVG(LENGTH(content))::int
                FROM messages
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
            """)

            return stats

        except Exception as e:
            logger.error(f"Failed to get message stats: {e}")
            return {'error': str(e)}


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_message_service: Optional[MessageService] = None


async def get_message_service() -> MessageService:
    """Get singleton message service instance"""
    global _message_service
    if _message_service is None:
        _message_service = MessageService()
        await _message_service.initialize()
    return _message_service
