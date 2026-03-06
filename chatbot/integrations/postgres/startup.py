"""
PostgreSQL Startup Integration for FastAPI

Add these startup/shutdown hooks to your FastAPI application to enable PostgreSQL support.

Usage in fastapi_chatbot.py:
    from chatbot.integrations.postgres.startup import (
        startup_postgres_stack,
        shutdown_postgres_stack,
        add_postgres_routes
    )

    @app.on_event("startup")
    async def startup():
        await startup_postgres_stack()

    @app.on_event("shutdown")
    async def shutdown():
        await shutdown_postgres_stack()

    # Add health check and admin routes
    add_postgres_routes(app)
"""

from fastapi import FastAPI, Depends, HTTPException
from typing import Dict, Any
import asyncio

from chatbot.integrations.postgres.client import pg_client, startup_postgres, shutdown_postgres
from chatbot.database.faq_service_postgres import startup_faq, shutdown_faq, get_faq_service
from chatbot.database.conversation_service import get_conversation_service
from chatbot.database.message_service import get_message_service
from chatbot.services.retrieval.pgvector_retriever import get_pgvector_retriever
from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def startup_postgres_stack():
    """
    Initialize entire PostgreSQL stack

    Call this in FastAPI startup event:
        @app.on_event("startup")
        async def startup():
            await startup_postgres_stack()
    """
    logger.info("🚀 Starting PostgreSQL stack...")

    if not settings.postgres_enabled:
        logger.warning("PostgreSQL disabled in settings (POSTGRES_ENABLED=false)")
        return

    try:
        # 1. PostgreSQL client
        await startup_postgres()

        # 2. FAQ Service
        await startup_faq()

        # 3. Conversation & Message Services
        conversation_service = await get_conversation_service()
        message_service = await get_message_service()

        # 4. pgvector retriever (if enabled)
        if settings.use_pgvector:
            pgvector = get_pgvector_retriever()
            logger.info("✅ pgvector retriever initialized")

        logger.info("✅ PostgreSQL stack initialized successfully")

    except Exception as e:
        logger.error(f"❌ Failed to initialize PostgreSQL stack: {e}", exc_info=True)
        # Don't raise - allow app to start with degraded functionality
        logger.warning("⚠️  Application starting with PostgreSQL unavailable")


async def shutdown_postgres_stack():
    """
    Shutdown PostgreSQL stack gracefully

    Call this in FastAPI shutdown event:
        @app.on_event("shutdown")
        async def shutdown():
            await shutdown_postgres_stack()
    """
    logger.info("👋 Shutting down PostgreSQL stack...")

    try:
        # 1. FAQ Service
        await shutdown_faq()

        # 2. PostgreSQL client
        await shutdown_postgres()

        logger.info("✅ PostgreSQL stack shutdown complete")

    except Exception as e:
        logger.error(f"Error during PostgreSQL shutdown: {e}")


def add_postgres_routes(app: FastAPI):
    """
    Add PostgreSQL health check and admin routes

    Usage:
        from chatbot.integrations.postgres.startup import add_postgres_routes

        app = FastAPI()
        add_postgres_routes(app)
    """

    @app.get("/api/health/postgres")
    async def postgres_health():
        """
        Check PostgreSQL health

        Returns:
            {
                "status": "healthy" | "unhealthy",
                "postgres": {...},
                "pgvector_enabled": bool
            }
        """
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

    @app.get("/api/stats/database")
    async def database_stats():
        """
        Get database statistics

        Returns:
            {
                "postgres": {...},
                "conversations": {...},
                "messages": {...},
                "embeddings": {...}
            }
        """
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

    @app.post("/api/admin/embeddings/cleanup")
    async def cleanup_embeddings():
        """
        Clean up expired embeddings

        Returns:
            {"deleted": int}
        """
        try:
            if not settings.use_pgvector:
                return {"deleted": 0, "message": "pgvector disabled"}

            pgvector = get_pgvector_retriever()
            deleted = await pgvector.cleanup_expired()

            return {
                "deleted": deleted,
                "message": f"Cleaned up {deleted} expired embeddings"
            }

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/admin/conversations/active")
    async def get_active_conversations(site_id: str = None, limit: int = 100):
        """
        Get active conversations

        Query params:
            site_id: Filter by site (optional)
            limit: Maximum results (default: 100)

        Returns:
            List of active conversation dicts
        """
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

    @app.get("/api/admin/conversation/{session_id}/messages")
    async def get_conversation_messages(session_id: str, limit: int = 50):
        """
        Get messages for a conversation

        Path params:
            session_id: Session identifier

        Query params:
            limit: Maximum messages (default: 50)

        Returns:
            {
                "session_id": str,
                "messages": [...],
                "count": int
            }
        """
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

    logger.info("✅ PostgreSQL routes added to FastAPI app")


# ============================================================================
# HELPER: Create Migration Script Runner
# ============================================================================

async def run_migrations():
    """
    Run database migrations (if using alembic)

    Call this before startup_postgres_stack():
        @app.on_event("startup")
        async def startup():
            await run_migrations()  # Optional
            await startup_postgres_stack()
    """
    try:
        logger.info("Running database migrations...")

        # Check if schema exists
        tables_exist = await pg_client.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'users'
            )
        """)

        if not tables_exist:
            logger.warning(
                "Database tables not found. "
                "Run: psql -U postgres -d chatbot -f chatbot/database/postgres_schema.sql"
            )

        logger.info("✅ Database schema verified")

    except Exception as e:
        logger.error(f"Migration check failed: {e}")
