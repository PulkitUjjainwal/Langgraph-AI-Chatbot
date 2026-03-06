"""
Embedding Service

Provides unified embedding generation for both FAISS and pgvector using Ollama.
"""

import asyncio
from typing import List, Union
import numpy as np

from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger
from chatbot.services.llm.ollama_client import get_ollama_client
from chatbot.utils.exceptions import EmbeddingError

logger = get_logger(__name__)
settings = get_settings()


class EmbeddingService:
    """
    Unified embedding service using Ollama

    Supports both sync and async usage for compatibility with FAISS and pgvector.
    """

    def __init__(self, ollama_client=None):
        """
        Initialize embedding service

        Args:
            ollama_client: Optional Ollama client instance (for dependency injection)
        """
        self.ollama_client = ollama_client or get_ollama_client()
        self.model = settings.embedding_model

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for text (synchronous)

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding

        Raises:
            EmbeddingError: If embedding generation fails
        """
        try:
            response = self.ollama_client.embeddings(
                model=self.model,
                prompt=text
            )

            # Extract embedding
            embedding = response.get('embeddings', [[]])[0]

            if not embedding:
                raise EmbeddingError("Empty embedding received from Ollama")

            return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise EmbeddingError(f"Embedding generation failed: {str(e)}") from e

    async def embed_text_async(self, text: str) -> List[float]:
        """
        Generate embedding for text (asynchronous)

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding

        Raises:
            EmbeddingError: If embedding generation fails
        """
        # Run sync embedding in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_text, text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (synchronous)

        Args:
            texts: List of texts to embed

        Returns:
            List of embeddings

        Raises:
            EmbeddingError: If embedding generation fails
        """
        embeddings = []
        for text in texts:
            embedding = self.embed_text(text)
            embeddings.append(embedding)
        return embeddings

    async def embed_batch_async(
        self,
        texts: List[str],
        max_concurrent: int = 5
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (asynchronous with concurrency limit)

        Args:
            texts: List of texts to embed
            max_concurrent: Maximum concurrent embedding requests

        Returns:
            List of embeddings

        Raises:
            EmbeddingError: If embedding generation fails
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def embed_with_semaphore(text: str) -> List[float]:
            async with semaphore:
                return await self.embed_text_async(text)

        # Process all texts concurrently (with limit)
        tasks = [embed_with_semaphore(text) for text in texts]
        return await asyncio.gather(*tasks)

    def embed_to_numpy(self, text: str, normalize: bool = True) -> np.ndarray:
        """
        Generate embedding as numpy array (for FAISS)

        Args:
            text: Text to embed
            normalize: Whether to L2-normalize the embedding

        Returns:
            Numpy array of shape (1, embedding_dim)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        import faiss

        embedding = self.embed_text(text)
        embedding_array = np.array([embedding]).astype('float32')

        if normalize:
            faiss.normalize_L2(embedding_array)

        return embedding_array

    async def embed_to_pgvector(self, text: str) -> List[float]:
        """
        Generate embedding for pgvector (async, no normalization)

        Args:
            text: Text to embed

        Returns:
            List of floats (suitable for pgvector)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        return await self.embed_text_async(text)

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this service

        Returns:
            Embedding dimension (768 for nomic-embed-text)
        """
        return settings.vector_dimension


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_embedding_service = None


def get_embedding_service() -> EmbeddingService:
    """Get singleton embedding service instance"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
