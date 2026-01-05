"""
Retrieval Services Package

Contains:
- KnowledgeBaseRetriever: Static FAISS-based KB retrieval
- HybridRetriever: Combined KB + dynamic content retrieval
- DynamicContentManager: Dynamic content fetching and embedding
"""

from chatbot.services.retrieval.kb_retriever import KnowledgeBaseRetriever
from chatbot.services.retrieval.hybrid_retriever import HybridRetriever
from chatbot.services.retrieval.dynamic_content import DynamicContentManager

__all__ = [
    'KnowledgeBaseRetriever',
    'HybridRetriever',
    'DynamicContentManager'
]
