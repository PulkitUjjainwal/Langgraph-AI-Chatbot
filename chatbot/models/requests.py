"""
Request Models for API Endpoints
"""

from typing import Optional
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


class ResetRequest(BaseModel):
    """Request model for reset endpoint"""
    session_id: str = Field(..., description="Session identifier to reset")
