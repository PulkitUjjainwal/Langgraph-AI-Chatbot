"""
FastAPI Request and Response Models

Pydantic models for API endpoints:
- Chat endpoints (request/response)
- Init endpoints (request/response)
- Session management
- Health checks
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str = Field(..., description="User's message", min_length=1)
    session_id: str = Field(..., description="Unique session identifier for conversation threading")
    dynamic_url: Optional[str] = Field(None, description="Optional dynamic URL to fetch data from")
    ip_address: Optional[str] = Field(None, description="Optional IP address of the client")

    class Config:
        json_schema_extra = {
            "example": {
                "message": "What is Export Genius?",
                "session_id": "user123",
                "dynamic_url": "https://www.exportgenius.in/company/example/abc123",
                "ip_address": "192.168.1.1"
            }
        }


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


class InitRequest(BaseModel):
    """Request model for init endpoint"""
    session_id: str = Field(..., description="Unique session identifier")
    dynamic_url: Optional[str] = Field(None, description="Optional dynamic URL to pre-cache")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user_123",
                "dynamic_url": "https://www.exportgenius.in/company/petron-corporation"
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
    session_id: Optional[str] = Field(None, description="Session identifier")

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
                "dynamic_url_processed": True,
                "session_id": "user_123"
            }
        }


class ResetRequest(BaseModel):
    """Request model for reset endpoint"""
    session_id: str = Field(..., description="Session identifier to reset")


class ResetResponse(BaseModel):
    """Response model for reset endpoint"""
    status: str
    session_id: str
    message: str


class HistoryResponse(BaseModel):
    """Response model for history endpoint"""
    session_id: str
    messages: List[Dict[str, str]]
    total_messages: int


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    version: str
    ollama_status: str
    kb_loaded: bool
    redis_connected: bool


class RedisStatsResponse(BaseModel):
    """Response model for Redis stats"""
    connected: bool
    total_keys: int
    memory_used: Optional[str] = None
    db_size: int
