"""
Production-Grade Ollama Client Service

Features:
- Lazy initialization
- Separate local (embeddings) and cloud (LLM) clients
- Connection pooling
- Error handling
- Logging
"""

import ollama
from typing import Dict, Any, Optional
from chatbot.config.settings import get_settings
from chatbot.config.logging_config import get_logger
from chatbot.utils.exceptions import OllamaConnectionError, EmbeddingError

logger = get_logger(__name__)


class OllamaClient:
    """
    Production-grade Ollama client with lazy initialization

    Manages two separate clients:
    - Local client: For fast embeddings (nomic-embed-text)
    - Cloud client: For LLM calls (deepseek-v3.1)
    """

    def __init__(self, settings: Optional[Any] = None):
        """
        Initialize Ollama client

        Args:
            settings: Settings instance (injected for testability)
        """
        self.settings = settings or get_settings()
        self._local_client: Optional[ollama.Client] = None
        self._cloud_client: Optional[ollama.Client] = None

    def _get_local_client(self) -> ollama.Client:
        """
        Lazy initialize the local Ollama client (for embeddings)

        Returns:
            Local Ollama client instance

        Raises:
            OllamaConnectionError: If connection fails
        """
        if self._local_client is None:
            try:
                self._local_client = ollama.Client(host="http://localhost:11434")
                logger.info("Initialized local Ollama client for embeddings")
            except Exception as e:
                logger.error(f"Failed to initialize local Ollama client: {e}", exc_info=True)
                raise OllamaConnectionError(
                    "Failed to connect to local Ollama. Ensure Ollama is running on localhost:11434"
                ) from e

        return self._local_client

    def _get_cloud_client(self) -> ollama.Client:
        """
        Lazy initialize the cloud Ollama client (for LLM)

        Returns:
            Cloud Ollama client instance

        Raises:
            OllamaConnectionError: If connection fails
        """
        if self._cloud_client is None:
            try:
                if self.settings.ollama_api_key:
                    # Use cloud API with authentication
                    self._cloud_client = ollama.Client(
                        host=self.settings.ollama_base_url,
                        headers={'Authorization': f'Bearer {self.settings.ollama_api_key}'}
                    )
                    logger.info(f"Initialized cloud Ollama client: {self.settings.ollama_base_url}")
                else:
                    # Fallback to local if no API key
                    self._cloud_client = ollama.Client(host="http://localhost:11434")
                    logger.warning("No Ollama API key found, using local client for LLM")
            except Exception as e:
                logger.error(f"Failed to initialize cloud Ollama client: {e}", exc_info=True)
                raise OllamaConnectionError(
                    f"Failed to connect to Ollama at {self.settings.ollama_base_url}"
                ) from e

        return self._cloud_client

    def embeddings(self, model: Optional[str] = None, prompt: str = "", **kwargs) -> Dict[str, Any]:
        """
        Generate embeddings using LOCAL Ollama (10-20x faster than OpenAI API)

        Args:
            model: Embedding model name (defaults to settings)
            prompt: Text to embed
            **kwargs: Additional arguments

        Returns:
            Embedding response with 'embeddings' key

        Raises:
            EmbeddingError: If embedding generation fails
        """
        model = model or kwargs.get('model', self.settings.embedding_model)
        prompt = prompt or kwargs.get('input', '')

        if not prompt:
            raise EmbeddingError("No text provided for embedding")

        try:
            # Use local Ollama client for embeddings (fast!)
            response = self._get_local_client().embeddings(
                model=model,
                prompt=prompt
            )

            # Convert Ollama format to match OpenAI format for compatibility
            # Ollama: {'embedding': [...]}
            # OpenAI: {'embeddings': [[...]]}
            if 'embedding' in response and 'embeddings' not in response:
                response['embeddings'] = [response['embedding']]

            logger.debug(f"Generated embedding for text ({len(prompt)} chars)")
            return response

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}", exc_info=True)
            raise EmbeddingError(f"Failed to generate embeddings: {str(e)}") from e

    def list_models(self) -> Dict[str, Any]:
        """
        List available models on local Ollama

        Returns:
            List of models
        """
        try:
            return self._get_local_client().list()
        except Exception as e:
            logger.error(f"Failed to list models: {e}", exc_info=True)
            raise OllamaConnectionError("Failed to list Ollama models") from e

    def pull_model(self, model_name: str) -> Dict[str, Any]:
        """
        Pull a model from Ollama registry

        Args:
            model_name: Name of the model to pull

        Returns:
            Pull response
        """
        try:
            logger.info(f"Pulling Ollama model: {model_name}")
            return self._get_local_client().pull(model_name)
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}", exc_info=True)
            raise OllamaConnectionError(f"Failed to pull model {model_name}") from e

    def get_cloud_client(self) -> ollama.Client:
        """
        Get the cloud client for direct LLM calls

        Returns:
            Cloud Ollama client instance
        """
        return self._get_cloud_client()

    def health_check(self) -> Dict[str, bool]:
        """
        Check health of Ollama connections

        Returns:
            Dict with health status of local and cloud clients
        """
        health = {
            "local": False,
            "cloud": False
        }

        # Check local
        try:
            self._get_local_client().list()
            health["local"] = True
        except Exception as e:
            logger.warning(f"Local Ollama health check failed: {e}")

        # Check cloud
        try:
            self._get_cloud_client()
            health["cloud"] = True
        except Exception as e:
            logger.warning(f"Cloud Ollama health check failed: {e}")

        return health


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_ollama_client: Optional[OllamaClient] = None


def get_ollama_client(settings: Optional[Any] = None) -> OllamaClient:
    """
    Get Ollama client instance (singleton pattern)

    Args:
        settings: Optional settings instance

    Returns:
        OllamaClient instance
    """
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient(settings)
    return _ollama_client


def get_ollama_cloud_client(settings: Optional[Any] = None) -> ollama.Client:
    """
    Get the cloud Ollama client for LLM calls

    Args:
        settings: Optional settings instance

    Returns:
        Cloud Ollama client
    """
    client = get_ollama_client(settings)
    return client.get_cloud_client()
