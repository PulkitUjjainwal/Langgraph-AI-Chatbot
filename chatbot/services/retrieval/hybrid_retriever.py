"""
Production-Grade Hybrid Retriever

Combines static knowledge base with dynamic content:
- Static KB (FAISS index) - fast, immutable, <100ms queries
- Dynamic embeddings (Redis cache) - session-specific, hot data
- Persistent embeddings (pgvector) - long-term, queryable, with metadata

Architecture:
    User Query
        │
        ├──> FAISS (Static KB)       ──> Fast <100ms
        ├──> Redis (Hot Cache)       ──> Session-specific
        └──> pgvector (PostgreSQL)   ──> Persistent, filterable
                    │
                    └──> Combined, ranked results
"""

import time
import asyncio
from typing import Dict, Any, List, Optional
import numpy as np
import faiss

from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger
from chatbot.services.retrieval.kb_retriever import KnowledgeBaseRetriever
from chatbot.integrations.redis.client import RedisMemoryManager
from chatbot.services.llm.ollama_client import get_ollama_client
from chatbot.services.retrieval.pgvector_retriever import get_pgvector_retriever

logger = get_logger(__name__)


class HybridRetriever:
    """
    Hybrid retrieval combining:
    1. Static KB (FAISS index) - ~2,300 chunks, <100ms queries
    2. Dynamic embeddings (Redis cache) - session-specific hot data
    3. Persistent embeddings (pgvector) - long-term queryable storage
    """

    def __init__(
        self,
        kb_retriever: KnowledgeBaseRetriever,
        redis_manager: RedisMemoryManager,
        settings=None,
        ollama_client=None,
        pgvector_retriever=None
    ):
        """
        Initialize Hybrid Retriever

        Args:
            kb_retriever: Knowledge base retriever instance (FAISS)
            redis_manager: Redis memory manager instance
            settings: Settings instance (for dependency injection)
            ollama_client: Ollama client instance (for dependency injection)
            pgvector_retriever: pgvector retriever instance (optional)
        """
        self.kb_retriever = kb_retriever
        self.redis = redis_manager
        self.settings = settings or get_settings()
        self.ollama_client = ollama_client or get_ollama_client()
        self.pgvector = pgvector_retriever or (
            get_pgvector_retriever() if self.settings.use_pgvector else None
        )

    async def retrieve_dynamic(
        self,
        query: str,
        session_id: str,
        dynamic_url: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve from dynamic embeddings in Redis

        Args:
            query: User query
            session_id: Session identifier
            dynamic_url: URL of dynamic content
            top_k: Number of results to return

        Returns:
            List of relevant chunks from dynamic content
        """
        # Get embeddings from Redis
        cached = self.redis.get_embeddings(session_id, dynamic_url)

        if not cached:
            logger.warning(
                f"No dynamic embeddings found in Redis for session: {session_id}",
                extra={"session_id": session_id, "url": dynamic_url}
            )
            return []

        # Unpack all three values (embeddings, chunks, full_content)
        embeddings, chunks, full_content = cached

        # Create temporary FAISS index
        index = faiss.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)

        # Generate query embedding using async wrapper
        try:
            response = await asyncio.to_thread(
                self.ollama_client.embeddings,
                model=self.settings.embedding_model,
                prompt=query
            )

            # Extract first embedding from the embeddings array
            query_embedding = np.array([response['embeddings'][0]]).astype('float32')
            faiss.normalize_L2(query_embedding)

        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}", exc_info=True)
            return []

        # Search
        scores, indices = index.search(query_embedding, min(top_k, len(chunks)))

        # Build results
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(chunks):
                chunk = chunks[idx].copy()
                chunk['score'] = float(scores[0][i])
                chunk['source'] = 'dynamic'
                chunk['page_title'] = 'Company Data'
                results.append(chunk)

        logger.debug(
            f"Retrieved {len(results)} dynamic chunks",
            extra={"session_id": session_id, "top_k": top_k}
        )

        return results

    async def hybrid_retrieve(
        self,
        query: str,
        session_id: str,
        dynamic_url: Optional[str] = None,
        kb_top_k: int = 3,
        dynamic_top_k: int = 3
    ) -> tuple[str, str]:
        """
        Hybrid retrieval from both KB and dynamic sources

        Args:
            query: User query
            session_id: Session identifier
            dynamic_url: Optional URL for dynamic content
            kb_top_k: Number of KB results
            dynamic_top_k: Number of dynamic results

        Returns:
            Tuple of (kb_context, dynamic_context)
        """
        start_time = time.time()
        logger.info(
            "Starting hybrid retrieval",
            extra={
                "query_length": len(query),
                "session_id": session_id,
                "has_dynamic_url": dynamic_url is not None
            }
        )

        # 1. KB Retrieval - Wrap in asyncio.to_thread to avoid blocking
        kb_results = await asyncio.to_thread(
            self.kb_retriever.retrieve,
            query,
            top_k=kb_top_k
        )
        kb_context = self.kb_retriever.format_context(kb_results)
        logger.debug(f"KB retrieval: {len(kb_results)} chunks")

        # 2. Dynamic Retrieval (if URL provided)
        dynamic_context = ""
        if dynamic_url:
            dynamic_results = await self.retrieve_dynamic(
                query,
                session_id,
                dynamic_url,
                top_k=dynamic_top_k
            )

            if dynamic_results:
                # Format dynamic context
                dynamic_parts = []
                for i, result in enumerate(dynamic_results, 1):
                    chunk_text = result['chunk_text']
                    if len(chunk_text) > self.settings.max_chunk_chars:
                        chunk_text = chunk_text[:self.settings.max_chunk_chars] + "..."
                    dynamic_parts.append(f"[Dynamic Source {i}]\n{chunk_text}\n")

                dynamic_context = "\n".join(dynamic_parts)
                logger.debug(f"Dynamic retrieval: {len(dynamic_results)} chunks")
            else:
                logger.debug("No dynamic embeddings available")

        elapsed = time.time() - start_time
        logger.info(
            f"Hybrid retrieval completed in {elapsed:.3f}s",
            extra={
                "kb_chunks": len(kb_results),
                "dynamic_chunks": len(dynamic_context) > 0,
                "elapsed": elapsed
            }
        )

        return kb_context, dynamic_context

    async def retrieve_pgvector(
        self,
        query: str,
        content_type: Optional[str] = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Retrieve from pgvector persistent storage

        Args:
            query: User query
            content_type: Filter by content type ('dynamic_url', 'user_message', etc.)
            top_k: Number of results to return

        Returns:
            List of relevant chunks from pgvector
        """
        if not self.settings.use_pgvector or not self.pgvector:
            logger.debug("pgvector disabled or not available")
            return []

        try:
            results = await self.pgvector.search_similar(
                query=query,
                content_type=content_type,
                top_k=top_k,
                similarity_threshold=self.settings.similarity_threshold
            )

            logger.debug(
                f"Retrieved {len(results)} chunks from pgvector",
                extra={"query_length": len(query), "content_type": content_type}
            )

            return results

        except Exception as e:
            logger.error(f"pgvector retrieval failed: {e}", exc_info=True)
            return []

    async def store_dynamic_content(
        self,
        content_id: str,
        content_text: str,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = None
    ) -> Optional[str]:
        """
        Store dynamic content in pgvector for persistent retrieval

        Args:
            content_id: Unique identifier for the content
            content_text: Text to embed and store
            metadata: Optional metadata (source, company_id, etc.)
            ttl_hours: Time-to-live in hours (default: 7 days)

        Returns:
            Embedding ID if successful, None otherwise

        Example:
            embedding_id = await retriever.store_dynamic_content(
                content_id="company_12345",
                content_text="Export statistics for machinery...",
                metadata={"source": "export_genius_api", "company_id": "12345"},
                ttl_hours=168  # 7 days
            )
        """
        if not self.settings.use_pgvector or not self.pgvector:
            logger.debug("pgvector disabled, content not stored")
            return None

        try:
            embedding_id = await self.pgvector.store_embedding(
                content_type="dynamic_url",
                content_id=content_id,
                content_text=content_text,
                metadata=metadata,
                ttl_hours=ttl_hours
            )

            logger.info(f"✅ Stored dynamic content in pgvector: {content_id}")
            return embedding_id

        except Exception as e:
            logger.error(f"Failed to store dynamic content: {e}", exc_info=True)
            return None

    async def hybrid_retrieve_v2(
        self,
        query: str,
        session_id: str,
        dynamic_url: Optional[str] = None,
        kb_top_k: int = 3,
        dynamic_top_k: int = 3,
        pgvector_top_k: int = 2,
        use_redis: bool = True,
        use_pgvector: bool = True
    ) -> Dict[str, Any]:
        """
        Enhanced hybrid retrieval from all three sources

        Architecture:
        1. FAISS: Static KB (fast, always enabled)
        2. Redis: Hot cache for current session
        3. pgvector: Persistent dynamic content with filtering

        Args:
            query: User query
            session_id: Session identifier
            dynamic_url: Optional URL for dynamic content
            kb_top_k: Number of KB results
            dynamic_top_k: Number of Redis dynamic results
            pgvector_top_k: Number of pgvector results
            use_redis: Enable Redis retrieval
            use_pgvector: Enable pgvector retrieval

        Returns:
            {
                'kb_context': str,
                'dynamic_context': str,
                'pgvector_context': str,
                'combined_context': str,
                'sources': ['static_kb', 'redis_cache', 'pgvector'],
                'chunks': {
                    'kb': [...],
                    'redis': [...],
                    'pgvector': [...]
                }
            }
        """
        start_time = time.time()
        logger.info(
            "Starting enhanced hybrid retrieval",
            extra={
                "query_length": len(query),
                "session_id": session_id,
                "has_dynamic_url": dynamic_url is not None,
                "use_redis": use_redis,
                "use_pgvector": use_pgvector
            }
        )

        # Parallel retrieval from all sources
        tasks = []
        task_map = {}

        # 1. FAISS (Static KB) - always enabled
        tasks.append(asyncio.to_thread(self.kb_retriever.retrieve, query, top_k=kb_top_k))
        task_map['kb'] = len(tasks) - 1

        # 2. Redis (Dynamic cache) - if URL provided and enabled
        if dynamic_url and use_redis:
            tasks.append(self.retrieve_dynamic(query, session_id, dynamic_url, top_k=dynamic_top_k))
            task_map['redis'] = len(tasks) - 1

        # 3. pgvector (Persistent storage) - if enabled
        if use_pgvector and self.settings.use_pgvector:
            tasks.append(self.retrieve_pgvector(query, content_type='dynamic_url', top_k=pgvector_top_k))
            task_map['pgvector'] = len(tasks) - 1

        # Execute all retrievals in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        kb_results = results[task_map['kb']] if 'kb' in task_map and not isinstance(results[task_map['kb']], Exception) else []
        redis_results = results[task_map['redis']] if 'redis' in task_map and not isinstance(results[task_map['redis']], Exception) else []
        pgvector_results = results[task_map['pgvector']] if 'pgvector' in task_map and not isinstance(results[task_map['pgvector']], Exception) else []

        # Format contexts
        kb_context = self.kb_retriever.format_context(kb_results)

        # Redis dynamic context
        dynamic_context = ""
        if redis_results:
            dynamic_parts = []
            for i, result in enumerate(redis_results, 1):
                chunk_text = result.get('chunk_text', '')
                if len(chunk_text) > self.settings.max_chunk_chars:
                    chunk_text = chunk_text[:self.settings.max_chunk_chars] + "..."
                dynamic_parts.append(f"[Dynamic Source {i} - Redis Cache]\n{chunk_text}\n")
            dynamic_context = "\n".join(dynamic_parts)

        # pgvector context
        pgvector_context = ""
        if pgvector_results:
            pgvector_parts = []
            for i, result in enumerate(pgvector_results, 1):
                content_text = result.get('content_text', '')
                similarity = result.get('similarity', 0)
                metadata = result.get('metadata', {})
                source = metadata.get('source', 'database')

                if len(content_text) > self.settings.max_chunk_chars:
                    content_text = content_text[:self.settings.max_chunk_chars] + "..."

                pgvector_parts.append(
                    f"[Persistent Source {i} - {source} (similarity: {similarity:.2f})]\n"
                    f"{content_text}\n"
                )
            pgvector_context = "\n".join(pgvector_parts)

        # Combine all contexts
        contexts = []
        sources = []

        if kb_context:
            contexts.append(f"=== Knowledge Base ===\n{kb_context}")
            sources.append('static_kb')

        if dynamic_context:
            contexts.append(f"\n=== Recent Dynamic Content (Session) ===\n{dynamic_context}")
            sources.append('redis_cache')

        if pgvector_context:
            contexts.append(f"\n=== Persistent Dynamic Content ===\n{pgvector_context}")
            sources.append('pgvector')

        combined_context = "\n\n".join(contexts)

        elapsed = time.time() - start_time
        logger.info(
            f"Enhanced hybrid retrieval completed in {elapsed:.3f}s",
            extra={
                "kb_chunks": len(kb_results),
                "redis_chunks": len(redis_results),
                "pgvector_chunks": len(pgvector_results),
                "sources": sources,
                "elapsed": elapsed
            }
        )

        return {
            'kb_context': kb_context,
            'dynamic_context': dynamic_context,
            'pgvector_context': pgvector_context,
            'combined_context': combined_context,
            'sources': sources,
            'chunks': {
                'kb': kb_results,
                'redis': redis_results,
                'pgvector': pgvector_results
            }
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get retrieval statistics from all sources

        Returns:
            Dict with stats from KB, Redis, and pgvector
        """
        stats = {
            "kb_stats": self.kb_retriever.get_stats(),
            "redis_stats": self.redis.get_stats()
        }

        if self.settings.use_pgvector and self.pgvector:
            # Add pgvector stats (async, so run in sync context)
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Can't get pgvector stats in sync context when loop is running
                    stats["pgvector_stats"] = {"status": "async_only"}
                else:
                    stats["pgvector_stats"] = loop.run_until_complete(self.pgvector.get_stats())
            except:
                stats["pgvector_stats"] = {"status": "unavailable"}

        return stats
