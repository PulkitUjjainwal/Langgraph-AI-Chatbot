"""
Credit System Models for Virtual Credit Tracking

Pydantic models for credit management:
- Credit state tracking
- Credit exhaustion responses
- Continue chat functionality
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime


class CreditState(BaseModel):
    """Current credit state for a session"""
    remaining: int = Field(..., description="Remaining credits")
    initial: int = Field(..., description="Initial credits allocated")
    used: int = Field(..., description="Credits used so far")
    continue_chat_used: bool = Field(default=False, description="Whether continue chat has been activated")
    multiplier: float = Field(default=1.0, description="Current credit multiplier")
    exhausted_at: Optional[datetime] = Field(None, description="Timestamp when credits were exhausted")
    last_deduction: Optional[datetime] = Field(None, description="Timestamp of last credit deduction")


class CreditDeductionResult(BaseModel):
    """Result of a credit deduction attempt"""
    success: bool = Field(..., description="Whether the deduction was successful")
    credits_remaining: int = Field(..., description="Credits remaining after deduction")
    credits_deducted: int = Field(..., description="Credits deducted in this operation")
    exhausted: bool = Field(default=False, description="Whether credits are now exhausted")
    state: CreditState = Field(..., description="Current credit state")


class CreditExhaustionResponse(BaseModel):
    """Response when credits are exhausted"""
    message: str = Field(..., description="Message to display to user")
    actions: List[Dict[str, str]] = Field(..., description="Available actions")
    show_continue_chat: bool = Field(default=True, description="Whether to show continue chat option")


class ContinueChatRequest(BaseModel):
    """Request to continue chat after exhaustion"""
    session_id: str = Field(..., description="Session identifier")


class ContinueChatResponse(BaseModel):
    """Response after activating continue chat"""
    status: str = Field(..., description="Status: success or error")
    credits_remaining: int = Field(..., description="Credits remaining after activation")
    message: str = Field(..., description="Confirmation message")


class CreditStatsResponse(BaseModel):
    """Credit usage statistics"""
    session_id: str
    total_sessions: int = Field(default=0)
    sessions_exhausted: int = Field(default=0)
    sessions_continued: int = Field(default=0)
    average_credits_used: float = Field(default=0.0)
