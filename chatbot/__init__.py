"""
Modular Chatbot Package

Production-grade architecture with:
- Configuration management
- Logging setup
- Services (LLM, Retrieval)
- Integrations (Redis, APIs, Web Scraping)
- Security (Hostility detection)
- Core workflow components
"""

from chatbot.config.settings import get_settings
from chatbot.config.logging_config import setup_logging, get_logger

__version__ = "2.0.0"
__all__ = ['get_settings', 'setup_logging', 'get_logger']
