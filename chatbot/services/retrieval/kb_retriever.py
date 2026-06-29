"""
Production-Grade Knowledge Base Retriever

Features:
- FAISS vector search
- Embedding caching
- Performance monitoring
- Error handling
- Logging
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
import faiss

from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger
from chatbot.utils.exceptions import KnowledgeBaseError, EmbeddingError
from chatbot.services.llm.ollama_client import get_ollama_client
from chatbot.utils.monitoring import timed_operation
import os

logger = get_logger(__name__)

# ============================================================================
# PROMETHEUS METRICS FOR QUERY EMBEDDING CACHE
# ============================================================================
METRICS_ENABLED = os.getenv("ENABLE_METRICS", "true").lower() == "true"

cache_ops_counter = None
if METRICS_ENABLED:
    try:
        from prometheus_client import Counter, REGISTRY
        # Try to get existing metric first, create if it doesn't exist
        try:
            cache_ops_counter = REGISTRY._names_to_collectors.get('cache_operations_total')
            if cache_ops_counter is None:
                cache_ops_counter = Counter(
                    'cache_operations_total',
                    'Total cache operations',
                    ['cache_type', 'result']
                )
            logger.info("Prometheus cache metrics enabled in KB retriever")
        except ValueError as e:
            # Metric already exists, try to retrieve it
            logger.warning(f"Cache metric already exists: {e}")
            cache_ops_counter = REGISTRY._names_to_collectors.get('cache_operations_total')
    except ImportError:
        logger.warning("prometheus_client not installed, cache metrics disabled")
        METRICS_ENABLED = False


class KnowledgeBaseRetriever:
    """
    RAG system using FAISS and Ollama embeddings

    Provides semantic search over knowledge base using vector similarity
    """

    def __init__(self, settings=None, ollama_client=None):
        """
        Initialize Knowledge Base Retriever

        Args:
            settings: Settings instance (for dependency injection)
            ollama_client: Ollama client instance (for dependency injection)
        """
        self.settings = settings or get_settings()
        self.ollama_client = ollama_client or get_ollama_client()

        self.index = None
        self.chunks = []
        self.embedding_cache = {}
        self.max_cache_size = 50

        self._load_knowledge_base()

    def _load_knowledge_base(self):
        """Load FAISS index and chunks from disk"""
        logger.info("Loading Knowledge Base...")

        # Load FAISS index
        if not self.settings.faiss_index_file.exists():
            raise KnowledgeBaseError(
                f"FAISS index not found: {self.settings.faiss_index_file}"
            )

        try:
            self.index = faiss.read_index(str(self.settings.faiss_index_file))
            logger.info(f"Loaded FAISS index: {self.settings.faiss_index_file}")
        except Exception as e:
            raise KnowledgeBaseError(
                f"Failed to load FAISS index: {str(e)}"
            ) from e

        # Load chunks
        if not self.settings.chunks_file.exists():
            raise KnowledgeBaseError(
                f"Chunks file not found: {self.settings.chunks_file}"
            )

        try:
            with open(self.settings.chunks_file, 'r', encoding='utf-8') as f:
                self.chunks = json.load(f)
            logger.info(f"Loaded {len(self.chunks)} chunks from KB")
        except Exception as e:
            raise KnowledgeBaseError(
                f"Failed to load chunks: {str(e)}"
            ) from e

    @timed_operation("faiss_retrieve")
    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks for a query

        Args:
            query: User query
            top_k: Number of results to return (defaults to settings)

        Returns:
            List of relevant chunks with scores

        Raises:
            EmbeddingError: If embedding generation fails
            KnowledgeBaseError: If retrieval fails
        """
        top_k = top_k or self.settings.top_k_results

        try:
            # Get or generate query embedding
            query_embedding = self._get_query_embedding(query)

            # Search FAISS index
            scores, indices = self.index.search(query_embedding, top_k)

            # Format results
            results = []
            for i, idx in enumerate(indices[0]):
                chunk = self.chunks[idx].copy()
                chunk['score'] = float(scores[0][i])
                results.append(chunk)

            logger.debug(
                f"Retrieved {len(results)} chunks",
                extra={"query_length": len(query), "top_k": top_k, "result_count": len(results)}
            )

            return results

        except EmbeddingError:
            raise
        except Exception as e:
            logger.error(f"Retrieval failed: {e}", exc_info=True)
            raise KnowledgeBaseError(f"Failed to retrieve chunks: {str(e)}") from e

    @timed_operation("query_embedding")
    def _get_query_embedding(self, query: str) -> np.ndarray:
        """
        Get or generate query embedding with caching

        Args:
            query: Query text

        Returns:
            Normalized query embedding
        """
        cache_key = query.strip().lower()

        # Check cache
        if cache_key in self.embedding_cache:
            logger.info(
                "Embedding cache hit",
                extra={
                    "cache_type": "query_embedding",
                    "cache_status": "hit"
                }
            )

            # Export to Prometheus (if enabled)
            if METRICS_ENABLED and cache_ops_counter:
                cache_ops_counter.labels(
                    cache_type="query_embedding",
                    result="hit"
                ).inc()

            return self.embedding_cache[cache_key]

        # Cache miss - generate new embedding
        logger.info(
            "Embedding cache miss",
            extra={
                "cache_type": "query_embedding",
                "cache_status": "miss"
            }
        )

        # Export to Prometheus (if enabled)
        if METRICS_ENABLED and cache_ops_counter:
            cache_ops_counter.labels(
                cache_type="query_embedding",
                result="miss"
            ).inc()

        try:
            response = self.ollama_client.embeddings(
                model=self.settings.embedding_model,
                prompt=query
            )

            # Extract and normalize embedding
            query_embedding = np.array([response['embeddings'][0]]).astype('float32')
            faiss.normalize_L2(query_embedding)

            # Cache it
            self._add_to_embedding_cache(cache_key, query_embedding)

            return query_embedding

        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}", exc_info=True)
            raise EmbeddingError(f"Query embedding failed: {str(e)}") from e

    def _add_to_embedding_cache(self, key: str, embedding: np.ndarray):
        """
        Add embedding to cache with LRU eviction

        Args:
            key: Cache key
            embedding: Embedding array
        """
        if len(self.embedding_cache) >= self.max_cache_size:
            # Remove oldest entry (first item)
            self.embedding_cache.pop(next(iter(self.embedding_cache)))

        self.embedding_cache[key] = embedding
        logger.debug(f"Cached embedding (cache size: {len(self.embedding_cache)})")

    def get_chunks(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get sample chunks from knowledge base

        Args:
            count: Number of chunks to return

        Returns:
            List of chunk dictionaries
        """
        return self.chunks[:count] if self.chunks else []

    def format_context(self, results: List[Dict[str, Any]]) -> str:
        """
        Format retrieved chunks as context string

        Args:
            results: List of retrieved chunks

        Returns:
            Formatted context string
        """
        context_parts = []

        for i, result in enumerate(results, 1):
            chunk_text = result.get('chunk_text', '')

            # Truncate if too long
            if len(chunk_text) > self.settings.max_chunk_chars:
                chunk_text = chunk_text[:self.settings.max_chunk_chars] + "..."

            page_title = result.get('page_title', 'Unknown Source')
            page_url = result.get('page_url', '')

            # Include URL if available
            if page_url:
                context_parts.append(
                    f"[Source {i}: {page_title}]\nURL: {page_url}\n{chunk_text}\n"
                )
            else:
                context_parts.append(
                    f"[Source {i}: {page_title}]\n{chunk_text}\n"
                )

        return "\n".join(context_parts)

    def is_loaded(self) -> bool:
        """Check if KB is loaded"""
        return self.index is not None and len(self.chunks) > 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get KB statistics

        Returns:
            Dict with KB stats
        """
        return {
            "total_chunks": len(self.chunks),
            "index_loaded": self.index is not None,
            "cache_size": len(self.embedding_cache),
            "faiss_index_path": str(self.settings.faiss_index_file),
            "chunks_file_path": str(self.settings.chunks_file)
        }
