"""
pgvector Retriever for Dynamic Content

Retrieves and stores dynamic embeddings using PostgreSQL's pgvector extension.
Complements FAISS (static KB) with dynamic, user-specific, and time-sensitive content.

Architecture:
- FAISS: Static knowledge base (~2,300 chunks, <100ms queries)
- pgvector: Dynamic content (API responses, user data, with TTL)
- Redis: Hot cache for both

Usage:
    retriever = PgVectorRetriever()

    # Store dynamic content
    await retriever.store_embedding(
        content_type="dynamic_url",
        content_id="company_12345",
        content_text="Export data for...",
        metadata={"source": "api", "company_id": "12345"},
        ttl_hours=168  # 7 days
    )

    # Search for similar content
    results = await retriever.search_similar(
        query="export statistics",
        content_type="dynamic_url",
        top_k=5,
        similarity_threshold=0.7
    )
"""

import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid

from chatbot.integrations.postgres.client import pg_client, get_postgres_client
from chatbot.services.embedding.embedding_service import get_embedding_service
from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


class PgVectorRetriever:
    """
    Retrieve and store dynamic embeddings using pgvector

    Features:
    - Vector similarity search using cosine distance
    - TTL-based automatic expiration
    - Metadata filtering
    - Async/await for performance
    """

    def __init__(self, embedding_service=None):
        """
        Initialize pgvector retriever

        Args:
            embedding_service: Optional embedding service instance
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self.dimension = settings.vector_dimension

    async def store_embedding(
        self,
        content_type: str,
        content_id: str,
        content_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = None
    ) -> str:
        """
        Store embedding in PostgreSQL

        Args:
            content_type: Type of content ('dynamic_url', 'user_message', 'faq', etc.)
            content_id: Unique identifier for the content
            content_text: Text to embed and store
            metadata: Optional metadata (JSON)
            ttl_hours: Time-to-live in hours (default from settings)

        Returns:
            UUID of the stored embedding

        Raises:
            Exception: If storage fails

        Example:
            embedding_id = await retriever.store_embedding(
                content_type="dynamic_url",
                content_id="company_12345",
                content_text="Export statistics for...",
                metadata={"source": "export_genius_api", "company_id": "12345"},
                ttl_hours=168
            )
        """
        try:
            # Generate embedding
            logger.debug(f"Generating embedding for {content_type}:{content_id}")
            embedding = await self.embedding_service.embed_to_pgvector(content_text)

            # Calculate expiration
            ttl = ttl_hours or settings.embedding_ttl_hours
            expires_at = None
            if ttl:
                expires_at = datetime.utcnow() + timedelta(hours=ttl)

            # Store in database
            embedding_id = await pg_client.fetchval("""
                INSERT INTO embeddings (
                    content_type,
                    content_id,
                    content_text,
                    embedding,
                    metadata,
                    expires_at
                )
                VALUES ($1, $2, $3, $4::vector, $5, $6)
                RETURNING id
            """, content_type, content_id, content_text, embedding, metadata or {}, expires_at)

            logger.info(
                f"✅ Stored embedding: {content_type}:{content_id} "
                f"(expires: {expires_at.isoformat() if expires_at else 'never'})"
            )
            return str(embedding_id)

        except Exception as e:
            logger.error(f"❌ Failed to store embedding for {content_type}:{content_id}: {e}")
            raise

    async def search_similar(
        self,
        query: str,
        content_type: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar embeddings using cosine similarity

        Args:
            query: Search query
            content_type: Filter by content type (None = search all types)
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0-1, default from settings)

        Returns:
            List of matching embeddings with metadata:
            [
                {
                    'id': UUID,
                    'content_type': str,
                    'content_id': str,
                    'content_text': str,
                    'metadata': dict,
                    'similarity': float (0-1),
                    'created_at': datetime
                },
                ...
            ]

        Example:
            results = await retriever.search_similar(
                query="export statistics for machinery",
                content_type="dynamic_url",
                top_k=5,
                similarity_threshold=0.7
            )

            for result in results:
                print(f"{result['similarity']:.2f} - {result['content_text'][:100]}")
        """
        try:
            # Generate query embedding
            logger.debug(f"Generating query embedding for: {query[:50]}...")
            query_embedding = await self.embedding_service.embed_to_pgvector(query)

            # Build query
            threshold = similarity_threshold or settings.similarity_threshold
            where_clause = "WHERE (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
            params = [query_embedding, top_k]
            param_idx = 3

            if content_type:
                where_clause += f" AND content_type = ${param_idx}"
                params.append(content_type)
                param_idx += 1

            sql = f"""
                SELECT
                    id,
                    content_type,
                    content_id,
                    content_text,
                    metadata,
                    1 - (embedding <=> $1::vector) as similarity,
                    created_at
                FROM embeddings
                {where_clause}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
            """

            # Execute search
            start_time = asyncio.get_event_loop().time()
            results = await pg_client.fetch(sql, *params)
            elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            # Filter by threshold and format
            matches = []
            for row in results:
                similarity = float(row['similarity'])
                if similarity >= threshold:
                    matches.append({
                        'id': str(row['id']),
                        'content_type': row['content_type'],
                        'content_id': row['content_id'],
                        'content_text': row['content_text'],
                        'metadata': row['metadata'],
                        'similarity': similarity,
                        'created_at': row['created_at']
                    })

            logger.info(
                f"🔍 Found {len(matches)}/{len(results)} embeddings above threshold "
                f"({threshold:.2f}) in {elapsed_ms:.1f}ms"
            )
            return matches

        except Exception as e:
            logger.error(f"❌ Vector search failed: {e}")
            return []

    async def get_by_content_id(
        self,
        content_id: str,
        content_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get embedding by content ID

        Args:
            content_id: Content identifier
            content_type: Optional content type filter

        Returns:
            Embedding dict or None if not found

        Example:
            embedding = await retriever.get_by_content_id("company_12345", "dynamic_url")
            if embedding:
                print(embedding['content_text'])
        """
        try:
            where_clause = "WHERE content_id = $1 AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
            params = [content_id]

            if content_type:
                where_clause += " AND content_type = $2"
                params.append(content_type)

            sql = f"""
                SELECT
                    id, content_type, content_id, content_text,
                    metadata, created_at, expires_at
                FROM embeddings
                {where_clause}
                LIMIT 1
            """

            row = await pg_client.fetchrow(sql, *params)

            if row:
                return {
                    'id': str(row['id']),
                    'content_type': row['content_type'],
                    'content_id': row['content_id'],
                    'content_text': row['content_text'],
                    'metadata': row['metadata'],
                    'created_at': row['created_at'],
                    'expires_at': row['expires_at']
                }
            return None

        except Exception as e:
            logger.error(f"❌ Failed to get embedding by content_id: {e}")
            return None

    async def delete_by_content_id(
        self,
        content_id: str,
        content_type: Optional[str] = None
    ) -> bool:
        """
        Delete embeddings by content ID

        Args:
            content_id: Content identifier
            content_type: Optional content type filter

        Returns:
            True if any embeddings were deleted

        Example:
            deleted = await retriever.delete_by_content_id("company_12345")
            print(f"Deleted: {deleted}")
        """
        try:
            where_clause = "WHERE content_id = $1"
            params = [content_id]

            if content_type:
                where_clause += " AND content_type = $2"
                params.append(content_type)

            result = await pg_client.execute(
                f"DELETE FROM embeddings {where_clause}",
                *params
            )

            deleted = int(result.split()[-1])
            if deleted > 0:
                logger.info(f"🗑️  Deleted {deleted} embeddings for content_id: {content_id}")
            return deleted > 0

        except Exception as e:
            logger.error(f"❌ Failed to delete embeddings: {e}")
            return False

    async def cleanup_expired(self) -> int:
        """
        Remove expired embeddings

        Returns:
            Number of embeddings deleted

        Example:
            deleted = await retriever.cleanup_expired()
            print(f"Cleaned up {deleted} expired embeddings")
        """
        try:
            result = await pg_client.execute("""
                DELETE FROM embeddings WHERE expires_at < CURRENT_TIMESTAMP
            """)

            deleted = int(result.split()[-1])
            if deleted > 0:
                logger.info(f"🧹 Cleaned up {deleted} expired embeddings")
            return deleted

        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored embeddings

        Returns:
            Dict with embedding statistics:
            {
                'total_embeddings': int,
                'by_content_type': {type: count},
                'expired_count': int,
                'avg_similarity': float (from recent searches)
            }

        Example:
            stats = await retriever.get_stats()
            print(f"Total embeddings: {stats['total_embeddings']}")
        """
        try:
            # Total count
            total = await pg_client.fetchval("SELECT COUNT(*) FROM embeddings")

            # Count by type
            by_type = await pg_client.fetch("""
                SELECT content_type, COUNT(*) as count
                FROM embeddings
                WHERE expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP
                GROUP BY content_type
            """)

            # Expired count
            expired = await pg_client.fetchval("""
                SELECT COUNT(*) FROM embeddings WHERE expires_at < CURRENT_TIMESTAMP
            """)

            return {
                'total_embeddings': total,
                'by_content_type': {row['content_type']: row['count'] for row in by_type},
                'expired_count': expired
            }

        except Exception as e:
            logger.error(f"❌ Failed to get stats: {e}")
            return {'error': str(e)}


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_pgvector_retriever = None


def get_pgvector_retriever() -> PgVectorRetriever:
    """Get singleton pgvector retriever instance"""
    global _pgvector_retriever
    if _pgvector_retriever is None:
        _pgvector_retriever = PgVectorRetriever()
    return _pgvector_retriever
