"""
PostgreSQL Integration for FastAPI Chatbot

This module provides integration functions to add PostgreSQL support to your existing
FastAPI chatbot without breaking anything.

Usage:
    In your fastapi_chatbot.py, add this after imports:

    from chatbot.integrations.postgres.fastapi_integration import (
        init_postgres_in_ensure_initialized,
        store_chat_interaction,
        add_postgres_to_router
    )

    Then follow the integration steps in FASTAPI_INTEGRATION_GUIDE.md
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from chatbot.integrations.postgres.client import pg_client
from chatbot.integrations.postgres.startup import startup_postgres_stack, shutdown_postgres_stack
from chatbot.database.conversation_service import get_conversation_service
from chatbot.database.message_service import get_message_service
from chatbot.database.faq_service_postgres import get_faq_service
from chatbot.services.retrieval.pgvector_retriever import get_pgvector_retriever
from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Track if PostgreSQL is available
_postgres_available = False


async def init_postgres_in_ensure_initialized():
    """
    Initialize PostgreSQL stack (safe to call multiple times)

    Add this to your ensure_initialized() function:
        await init_postgres_in_ensure_initialized()

    Returns:
        bool: True if PostgreSQL is available
    """
    global _postgres_available

    if not settings.postgres_enabled:
        logger.info("PostgreSQL disabled in settings")
        return False

    try:
        # Initialize PostgreSQL stack
        await startup_postgres_stack()
        _postgres_available = True
        logger.info("✅ PostgreSQL stack initialized")
        return True
    except Exception as e:
        logger.warning(f"PostgreSQL initialization failed: {e}")
        logger.warning("Continuing without PostgreSQL (Redis-only mode)")
        _postgres_available = False
        return False


async def store_chat_interaction(
    session_id: str,
    user_message: str,
    assistant_response: str,
    metadata: Optional[Dict[str, Any]] = None,
    site_id: Optional[str] = None
) -> bool:
    """
    Store chat interaction in PostgreSQL

    Add this after getting LLM response in your /chat endpoint:
        await store_chat_interaction(
            session_id=session_id,
            user_message=user_query,
            assistant_response=response,
            metadata={"processing_time_ms": processing_time}
        )

    Args:
        session_id: Session identifier
        user_message: User's message
        assistant_response: Bot's response
        metadata: Optional metadata (sources, timing, etc.)
        site_id: Site identifier (defaults to settings.site_id)

    Returns:
        bool: True if stored successfully, False if PostgreSQL unavailable
    """
    if not _postgres_available:
        return False

    try:
        # Create/update conversation
        conversation_service = await get_conversation_service()
        conversation_id = await conversation_service.create_conversation(
            session_id=session_id,
            site_id=site_id or settings.site_id,
            metadata=metadata or {}
        )

        # Store user message
        message_service = await get_message_service()
        await message_service.store_message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            metadata={}
        )

        # Store assistant response
        await message_service.store_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_response,
            metadata=metadata or {}
        )

        # Update conversation activity
        await conversation_service.update_activity(session_id)

        logger.debug(f"Stored chat interaction for session: {session_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to store chat interaction: {e}")
        return False


async def store_dynamic_content_in_pgvector(
    content_id: str,
    content_text: str,
    metadata: Optional[Dict[str, Any]] = None,
    ttl_hours: int = 168
) -> Optional[str]:
    """
    Store dynamic content in pgvector for persistent retrieval

    Add this after fetching dynamic content:
        if dynamic_content and settings.use_pgvector:
            await store_dynamic_content_in_pgvector(
                content_id=f"company_{company_id}",
                content_text=dynamic_content,
                metadata={"source": "api", "company_id": company_id}
            )

    Args:
        content_id: Unique identifier
        content_text: Text to embed
        metadata: Optional metadata
        ttl_hours: Time to live in hours (default: 7 days)

    Returns:
        str: Embedding ID if successful, None otherwise
    """
    if not _postgres_available or not settings.use_pgvector:
        return None

    try:
        pgvector = get_pgvector_retriever()
        embedding_id = await pgvector.store_embedding(
            content_type="dynamic_url",
            content_id=content_id,
            content_text=content_text,
            metadata=metadata,
            ttl_hours=ttl_hours
        )

        logger.info(f"Stored dynamic content in pgvector: {content_id}")
        return embedding_id

    except Exception as e:
        logger.error(f"Failed to store dynamic content: {e}")
        return None


def add_postgres_to_router(router):
    """
    Add PostgreSQL health and admin endpoints to FastAPI router

    Usage:
        from fastapi import APIRouter
        router = APIRouter(prefix="/api")

        # Add your existing routes...

        # Add PostgreSQL routes
        from chatbot.integrations.postgres.fastapi_integration import add_postgres_to_router
        add_postgres_to_router(router)

    Args:
        router: FastAPI APIRouter instance
    """
    from fastapi import HTTPException

    @router.get("/health/postgres")
    async def postgres_health():
        """PostgreSQL health check"""
        if not _postgres_available:
            return {
                "status": "disabled",
                "message": "PostgreSQL is disabled or unavailable"
            }

        try:
            health = await pg_client.health_check()
            return {
                "status": health['status'],
                "postgres": health,
                "pgvector_enabled": settings.use_pgvector
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    @router.get("/stats/database")
    async def database_stats():
        """Get database statistics"""
        if not _postgres_available:
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL not available"
            )

        try:
            stats = {}

            # PostgreSQL stats
            stats['postgres'] = await pg_client.get_stats()

            # Conversation stats
            conversation_service = await get_conversation_service()
            stats['conversations'] = await conversation_service.get_stats()

            # Message stats
            message_service = await get_message_service()
            stats['messages'] = await message_service.get_stats()

            # pgvector stats
            if settings.use_pgvector:
                pgvector = get_pgvector_retriever()
                stats['embeddings'] = await pgvector.get_stats()

            return stats

        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/conversations/active")
    async def get_active_conversations(site_id: str = None, limit: int = 100):
        """Get active conversations"""
        if not _postgres_available:
            raise HTTPException(status_code=503, detail="PostgreSQL not available")

        try:
            conversation_service = await get_conversation_service()
            conversations = await conversation_service.get_active_conversations(
                site_id=site_id,
                limit=limit
            )

            return {
                "conversations": conversations,
                "count": len(conversations)
            }

        except Exception as e:
            logger.error(f"Failed to get active conversations: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/admin/conversation/{session_id}/messages")
    async def get_conversation_messages(session_id: str, limit: int = 50):
        """Get messages for a conversation"""
        if not _postgres_available:
            raise HTTPException(status_code=503, detail="PostgreSQL not available")

        try:
            # Get conversation
            conversation_service = await get_conversation_service()
            conversation = await conversation_service.get_conversation(session_id)

            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

            # Get messages
            message_service = await get_message_service()
            messages = await message_service.get_conversation_messages(
                conversation_id=conversation['id'],
                limit=limit
            )

            return {
                "session_id": session_id,
                "conversation": conversation,
                "messages": messages,
                "count": len(messages)
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to get conversation messages: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/admin/embeddings/cleanup")
    async def cleanup_embeddings():
        """Clean up expired embeddings"""
        if not _postgres_available or not settings.use_pgvector:
            return {"deleted": 0, "message": "pgvector disabled"}

        try:
            pgvector = get_pgvector_retriever()
            deleted = await pgvector.cleanup_expired()

            return {
                "deleted": deleted,
                "message": f"Cleaned up {deleted} expired embeddings"
            }

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("✅ PostgreSQL routes added to router")


async def shutdown_postgres():
    """
    Shutdown PostgreSQL gracefully

    Add this to your shutdown handler:
        await shutdown_postgres()
    """
    if _postgres_available:
        await shutdown_postgres_stack()


def is_postgres_available() -> bool:
    """Check if PostgreSQL is available"""
    return _postgres_available
