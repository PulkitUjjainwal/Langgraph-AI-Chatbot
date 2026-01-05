"""
Production-Grade Configuration Module

Uses Pydantic Settings for:
- Type validation
- Environment variable parsing
- 12-factor app compliance
- Clear defaults
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import Field

# Try importing from pydantic_settings (Pydantic V2)
# Fall back to pydantic if not available (Pydantic V1)
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

# Try importing validator (Pydantic V1) or field_validator (Pydantic V2)
try:
    from pydantic import field_validator
except ImportError:
    from pydantic import validator as field_validator


class Settings(BaseSettings):
    """Application settings with validation and environment variable support"""

    # ============================================================================
    # SITE IDENTIFICATION
    # ============================================================================
    site_id: str = Field(default="exportgenius", env="SITE_ID")
    site_name: str = Field(default="Export Genius", env="SITE_NAME")

    # ============================================================================
    # DATA FILES
    # ============================================================================
    data_dir: Path = Field(default=Path("data"))

    # Dynamically constructed based on site_id
    @property
    def chunks_file(self) -> Path:
        """Get KB chunks file path for current site"""
        custom_path = os.getenv("KB_CHUNKS_FILE")
        if custom_path:
            return Path(custom_path)
        return self.data_dir / f"kb_{self.site_id}_chunks.json"

    @property
    def faiss_index_file(self) -> Path:
        """Get FAISS index file path for current site"""
        custom_path = os.getenv("FAISS_INDEX_FILE")
        if custom_path:
            return Path(custom_path)
        return self.data_dir / f"faiss_{self.site_id}_normalized.index"

    # ============================================================================
    # LLM CONFIGURATION
    # ============================================================================
    embedding_model: str = Field(default="nomic-embed-text", env="EMBEDDING_MODEL")
    llm_model: str = Field(default="deepseek-v3.1:671b-cloud", env="LLM_MODEL")

    # LLM Parameters
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.8, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1)
    num_predict: int = Field(default=650, ge=1)
    num_ctx: int = Field(default=3400, ge=1)

    # ============================================================================
    # RETRIEVAL CONFIGURATION
    # ============================================================================
    top_k_results: int = Field(default=5, ge=1, le=20)
    max_chunk_chars: int = Field(default=800, ge=100)
    dynamic_max_chunks: int = Field(default=10, ge=1, le=50)

    # ============================================================================
    # OLLAMA CONFIGURATION
    # ============================================================================
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_api_key: Optional[str] = Field(default=None, env="OLLAMA_API_KEY")
    ollama_timeout: float = Field(default=30.0, ge=1.0)

    # ============================================================================
    # REDIS CONFIGURATION
    # ============================================================================
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT", ge=1, le=65535)
    redis_db: int = Field(default=0, env="REDIS_DB", ge=0)
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_ttl_days: int = Field(default=7, env="REDIS_TTL_DAYS", ge=1)

    # ============================================================================
    # SESSION MANAGEMENT
    # ============================================================================
    session_timeout_minutes: int = Field(default=30, ge=1)
    max_sessions: int = Field(default=1000, ge=1)

    # ============================================================================
    # PERFORMANCE & OPTIMIZATION
    # ============================================================================
    enable_performance_logging: bool = Field(default=True)
    disable_checkpointing: bool = Field(default=False, env="DISABLE_CHECKPOINTING")
    max_concurrent_embeddings: int = Field(default=5, ge=1, le=20)

    # ============================================================================
    # API CONFIGURATION
    # ============================================================================
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT", ge=1, le=65535)
    api_prefix: str = Field(default="/api")
    api_version: str = Field(default="v1")

    # ============================================================================
    # EXPORT GENIUS API
    # ============================================================================
    export_genius_bearer_token: Optional[str] = Field(
        default=None,
        env="EXPORT_GENIUS_BEARER_TOKEN"
    )
    export_genius_api_timeout: int = Field(default=30, ge=1)
    export_genius_max_retries: int = Field(default=3, ge=0, le=10)

    # ============================================================================
    # LOGGING
    # ============================================================================
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json")  # json or text

    # ============================================================================
    # ENVIRONMENT
    # ============================================================================
    environment: str = Field(default="development", env="ENVIRONMENT")
    debug: bool = Field(default=False, env="DEBUG")

    # Note: Validators removed for simplicity
    # Can add back with @field_validator if needed

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"  # Ignore extra fields from .env
    }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings instance (singleton pattern)"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Convenience function for backward compatibility
def get_config() -> Settings:
    """Alias for get_settings() for backward compatibility"""
    return get_settings()
