"""
Response Models for API Endpoints
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str = Field(..., description="Bot's response")
    session_id: str = Field(..., description="Session identifier")
    processing_time: float = Field(..., description="Processing time in seconds")
    sources_used: List[str] = Field(default_factory=list, description="Sources used for response")

    class Config:
        json_schema_extra = {
            "example": {
                "response": "Export Genius is a global trade intelligence platform...",
                "session_id": "user123",
                "processing_time": 2.34,
                "sources_used": ["Knowledge Base", "Dynamic Content"]
            }
        }


class InitResponse(BaseModel):
    """Response model for init endpoint"""
    status: str = Field(..., description="Status: success, partial_success, or error")
    suggested_questions: List[str] = Field(..., description="5 suggested questions for the user")
    cache_status: Dict[str, Any] = Field(..., description="Cache information")
    processing_time: float = Field(..., description="Processing time in seconds")
    dynamic_url_processed: bool = Field(..., description="Whether dynamic URL was processed")
    error: Optional[str] = Field(None, description="Error message if any")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "suggested_questions": [
                    "What products does Petron Corporation import?",
                    "Show me Petron's top trading partners",
                    "What is Petron's trade volume trend?",
                    "Tell me about Petron's recent shipments",
                    "How can Export Genius help analyze this company?"
                ],
                "cache_status": {
                    "cache_hit": False,
                    "cached_at": "2025-12-03T12:00:00Z"
                },
                "processing_time": 15.2,
                "dynamic_url_processed": True
            }
        }


class HistoryResponse(BaseModel):
    """Response model for history endpoint"""
    session_id: str
    messages: List[Dict[str, str]]
    total_messages: int


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    ollama_status: str
    kb_loaded: bool
    active_sessions: int
    uptime_seconds: float


class RedisStatsResponse(BaseModel):
    """Response model for Redis stats endpoint"""
    conversations: int
    embeddings: int
    sessions: int
    memory_used_mb: float
    redis_info: Dict[str, Any]
