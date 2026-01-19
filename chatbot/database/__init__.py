"""Database package for chatbot FAQ system"""

from .faq_service import FAQService, get_faq_service

__all__ = ["FAQService", "get_faq_service"]
