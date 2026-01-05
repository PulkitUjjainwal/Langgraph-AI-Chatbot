"""
OpenAI Embeddings Provider
Production-grade wrapper for OpenAI's embedding API
"""

import os
import time
from typing import List, Union
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class OpenAIEmbeddings:
    """
    Wrapper for OpenAI embeddings API

    Provides same interface as previous embedding providers
    Uses text-embedding-3-small for optimal cost/performance
    """

    def __init__(self, model_name: str = "text-embedding-3-small", timeout: float = 30.0):
        """
        Initialize OpenAI embeddings client

        Args:
            model_name: OpenAI embedding model
                       Options:
                       - text-embedding-3-small (1536 dim, $0.02/1M tokens) - RECOMMENDED
                       - text-embedding-3-large (3072 dim, $0.13/1M tokens)
                       - text-embedding-ada-002 (1536 dim, $0.10/1M tokens) - Legacy
            timeout: Timeout in seconds for API calls (default: 30s)
        """
        self._model_name = model_name
        self._timeout = timeout
        self._api_key = os.getenv("OPENAI_API_KEY")

        if not self._api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment variables. "
                "Please add it to your .env file: OPENAI_API_KEY=sk-..."
            )

        # CRITICAL FIX: Add timeout to prevent hanging
        self._client = OpenAI(api_key=self._api_key, timeout=timeout)
        print(f"[OPENAI-EMBED] Initialized OpenAI embeddings: {model_name} (timeout: {timeout}s)")

    def embeddings(self, prompt: Union[str, List[str]], **kwargs) -> dict:
        """
        Generate embeddings (compatible with existing interface)

        Args:
            prompt: Single text or list of texts
            **kwargs: Ignored (for compatibility)

        Returns:
            dict with 'embeddings' key containing list of embedding vectors
        """
        # Convert single string to list for consistent processing
        is_single = isinstance(prompt, str)
        texts = [prompt] if is_single else prompt

        # Filter out empty strings
        texts = [t for t in texts if t and t.strip()]

        if not texts:
            raise ValueError("No valid text provided for embedding")

        # Truncate long texts to stay under 8192 token limit
        # Rough estimate: 1 token ~= 4 characters, but some text is denser
        # Use 15,000 chars to be very conservative (guarantees < 8192 tokens)
        MAX_CHARS = 15000
        texts = [t[:MAX_CHARS] if len(t) > MAX_CHARS else t for t in texts]

        # Generate embeddings via OpenAI API
        start = time.time()

        # Log batch info
        total_chars = sum(len(t) for t in texts)
        print(f"[OPENAI-EMBED] Requesting {len(texts)} embeddings (~{total_chars:,} chars)...")

        try:
            response = self._client.embeddings.create(
                model=self._model_name,
                input=texts,
                encoding_format="float"  # Return as float array
            )

            elapsed = time.time() - start

            # Extract embeddings from response
            embeddings_list = [item.embedding for item in response.data]

            # Calculate tokens used
            total_tokens = response.usage.total_tokens

            print(f"[OPENAI-EMBED] ✓ Generated {len(embeddings_list)} embeddings in {elapsed:.3f}s "
                  f"({len(embeddings_list)/elapsed:.1f} emb/s, {total_tokens} tokens)")

            return {
                'embeddings': embeddings_list,
                'model': self._model_name,
                'total_duration': int(elapsed * 1e9),  # nanoseconds
                'tokens_used': total_tokens
            }

        except TimeoutError as e:
            elapsed = time.time() - start
            print(f"[OPENAI-EMBED] ✗ TIMEOUT after {elapsed:.1f}s - {len(texts)} texts, {total_chars:,} chars")
            print(f"[OPENAI-EMBED] Consider reducing batch size or increasing timeout")
            raise TimeoutError(f"OpenAI embedding timeout after {elapsed:.1f}s") from e
        except Exception as e:
            elapsed = time.time() - start
            print(f"[OPENAI-EMBED] ✗ ERROR after {elapsed:.1f}s: {type(e).__name__}: {e}")
            raise

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings"""
        if "small" in self._model_name or "ada-002" in self._model_name:
            return 1536
        elif "large" in self._model_name:
            return 3072
        else:
            # Default to 1536 for unknown models
            return 1536


# Global instance
_openai_embeddings = None


def get_openai_embeddings():
    """Get or create global OpenAI embeddings instance"""
    global _openai_embeddings
    if _openai_embeddings is None:
        _openai_embeddings = OpenAIEmbeddings()
    return _openai_embeddings
