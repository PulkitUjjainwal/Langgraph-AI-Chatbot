"""
Production-Grade Hybrid Retriever

Combines static knowledge base with dynamic content:
- Static KB (FAISS index)
- Dynamic embeddings (from Redis cache)
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

logger = get_logger(__name__)


class HybridRetriever:
    """
    Hybrid retrieval combining:
    1. Static KB (FAISS index)
    2. Dynamic embeddings (from Redis)
    """

    def __init__(
        self,
        kb_retriever: KnowledgeBaseRetriever,
        redis_manager: RedisMemoryManager,
        settings=None,
        ollama_client=None
    ):
        """
        Initialize Hybrid Retriever

        Args:
            kb_retriever: Knowledge base retriever instance
            redis_manager: Redis memory manager instance
            settings: Settings instance (for dependency injection)
            ollama_client: Ollama client instance (for dependency injection)
        """
        self.kb_retriever = kb_retriever
        self.redis = redis_manager
        self.settings = settings or get_settings()
        self.ollama_client = ollama_client or get_ollama_client()

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

    def get_stats(self) -> Dict[str, Any]:
        """
        Get retrieval statistics

        Returns:
            Dict with stats
        """
        return {
            "kb_stats": self.kb_retriever.get_stats(),
            "redis_stats": self.redis.get_stats()
        }
