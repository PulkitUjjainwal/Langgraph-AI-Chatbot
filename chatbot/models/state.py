"""
State Models for LangGraph Workflow
"""

from typing import TypedDict, Annotated, Sequence
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    State passed between nodes in LangGraph workflow

    Attributes:
        messages: Conversation history
        next_agent: Next agent to route to
        retrieved_context: Retrieved context from KB or dynamic sources
        original_query: Original user query
        use_cache: Whether to use caching
        retrieved_chunks: List of retrieved chunks
        start_time: Timestamp when request started
        session_id: Session identifier
        dynamic_url: Optional dynamic URL for data fetching
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next_agent: str
    retrieved_context: str
    original_query: str
    use_cache: bool
    retrieved_chunks: list
    start_time: float
    session_id: str
    dynamic_url: str
