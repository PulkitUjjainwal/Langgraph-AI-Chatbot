"""
Custom Exception Classes for Production Error Handling
"""


class ChatbotException(Exception):
    """Base exception for chatbot errors"""
    pass


class ConfigurationError(ChatbotException):
    """Raised when configuration is invalid"""
    pass


class OllamaConnectionError(ChatbotException):
    """Raised when unable to connect to Ollama"""
    pass


class RedisConnectionError(ChatbotException):
    """Raised when unable to connect to Redis"""
    pass


class KnowledgeBaseError(ChatbotException):
    """Raised when knowledge base operations fail"""
    pass


class EmbeddingError(ChatbotException):
    """Raised when embedding generation fails"""
    pass


class APIConnectionError(ChatbotException):
    """Raised when external API calls fail"""
    pass


class RetrievalError(ChatbotException):
    """Raised when retrieval operations fail"""
    pass


class SessionError(ChatbotException):
    """Raised when session operations fail"""
    pass


class ValidationError(ChatbotException):
    """Raised when input validation fails"""
    pass


class DynamicContentError(ChatbotException):
    """Raised when dynamic content fetching fails"""
    pass
