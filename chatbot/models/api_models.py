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
                "message": "What is Market Inside?",
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
    lead_prompt: Optional[Dict[str, Any]] = Field(None, description="Lead capture form config if needed")

    class Config:
        json_schema_extra = {
            "example": {
                "response": "Market Inside is a global trade intelligence platform...",
                "session_id": "user123",
                "processing_time": 2.34,
                "sources_used": ["Knowledge Base", "Dynamic Content"],
                "lead_prompt": {
                    "show_form": True,
                    "prompt_type": "high_intent",
                    "message": "I can send you this detailed information. What's your email?",
                    "fields": [
                        {"name": "email", "type": "email", "required": True},
                        {"name": "phone", "type": "tel", "required": False}
                    ]
                }
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
    version: str = Field(default="3.0.0", description="API version")
    ollama_status: str
    kb_loaded: bool
    redis_connected: bool
    active_sessions: Optional[int] = Field(default=0, description="Number of active sessions")
    uptime_seconds: Optional[float] = Field(default=0.0, description="Server uptime in seconds")
    version: str
    redis_connected: bool


class RedisStatsResponse(BaseModel):
    """Response model for Redis stats"""
    connected: bool
    total_keys: int
    memory_used: Optional[str] = None
    db_size: int


# ============================================================================
# LEAD CAPTURE MODELS
# ============================================================================

class LeadCaptureRequest(BaseModel):
    """Request model for lead capture endpoint"""
    session_id: str = Field(..., description="Session identifier")
    email: str = Field(..., description="User's email address")
    phone: Optional[str] = Field(None, description="User's phone number")
    company_name: Optional[str] = Field(None, description="User's company name")
    name: Optional[str] = Field(None, description="User's name")
    source_url: Optional[str] = Field(None, description="Page URL where lead was captured")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "email": "john@example.com",
                "phone": "+1234567890",
                "company_name": "Acme Corp",
                "name": "John Doe",
                "source_url": "https://marketinside.com/company/xyz"
            }
        }


class LeadCaptureResponse(BaseModel):
    """Response model for lead capture endpoint"""
    status: str = Field(..., description="Status: success or error")
    message: str = Field(..., description="Response message")
    session_id: str = Field(..., description="Session identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Thank you! I'll send you personalized insights.",
                "session_id": "user123"
            }
        }


class LeadSkipRequest(BaseModel):
    """Request model for lead skip endpoint"""
    session_id: str = Field(..., description="Session identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123"
            }
        }


class LeadSkipResponse(BaseModel):
    """Response model for lead skip endpoint"""
    status: str = Field(..., description="Status: success")
    message: str = Field(..., description="Response message")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "No problem! Let me know if you change your mind."
            }
        }


class LeadStatsResponse(BaseModel):
    """Response model for lead stats endpoint"""
    total_leads: int = Field(..., description="Total number of captured leads")
    leads: Optional[List[Dict[str, Any]]] = Field(None, description="List of leads (if requested)")

    class Config:
        json_schema_extra = {
            "example": {
                "total_leads": 150,
                "leads": [
                    {
                        "email": "john@example.com",
                        "company_name": "Acme Corp",
                        "captured_at": "2025-01-15T10:30:00Z"
                    }
                ]
            }
        }


# ============================================================================
# FEEDBACK MODELS
# ============================================================================

class ConversationMessageModel(BaseModel):
    """Model for a single conversation message"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    message_id: Optional[str] = Field(None, description="Optional message ID")


class FeedbackRequest(BaseModel):
    """Request model for feedback endpoint"""
    session_id: str = Field(..., description="Session identifier")
    feedback_type: str = Field(..., description="Type: 'thumbs_up', 'thumbs_down', 'rating', 'comment'")
    rating: Optional[int] = Field(None, description="1-5 rating (for rating type)", ge=1, le=5)
    comment: Optional[str] = Field(None, description="Optional user comment")
    message_id: Optional[str] = Field(None, description="ID of the message being rated")
    assistant_message: Optional[str] = Field(None, description="The assistant response that was rated")
    user_query: Optional[str] = Field(None, description="The user question that triggered the response")
    page_url: Optional[str] = Field(None, description="Page URL where feedback was given")
    conversation: Optional[List[ConversationMessageModel]] = Field(None, description="Full conversation history")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "feedback_type": "thumbs_down",
                "comment": "The response was not accurate",
                "message_id": "msg_456",
                "assistant_message": "Market Inside is a platform...",
                "user_query": "What is Market Inside?",
                "page_url": "https://marketinsidedata.com/",
                "conversation": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi! How can I help?"},
                    {"role": "user", "content": "What is Market Inside?"},
                    {"role": "assistant", "content": "Market Inside is a platform..."}
                ]
            }
        }


class FeedbackResponse(BaseModel):
    """Response model for feedback endpoint"""
    success: bool = Field(..., description="Whether feedback was stored successfully")
    feedback_id: Optional[int] = Field(None, description="Database ID of the stored feedback")
    message: str = Field(..., description="Response message")
    storage: Optional[str] = Field(None, description="Storage type: 'mysql' or 'file'")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "feedback_id": 123,
                "message": "Thank you for your feedback!",
                "storage": "mysql"
            }
        }


class FeedbackStatsResponse(BaseModel):
    """Response model for feedback stats endpoint"""
    period_days: int = Field(..., description="Number of days in the stats period")
    total_feedback: int = Field(..., description="Total feedback entries")
    by_type: Dict[str, int] = Field(..., description="Feedback count by type")
    avg_rating: Optional[float] = Field(None, description="Average rating (if ratings exist)")

    class Config:
        json_schema_extra = {
            "example": {
                "period_days": 30,
                "total_feedback": 250,
                "by_type": {
                    "thumbs_up": 180,
                    "thumbs_down": 45,
                    "rating": 20,
                    "comment": 5
                },
                "avg_rating": 4.2
            }
        }


# ============================================================================
# FEEDBACK MANAGEMENT MODELS (Admin/Dashboard)
# ============================================================================

class FeedbackListItem(BaseModel):
    """Single feedback item for list view"""
    id: int
    session_id: str
    feedback_type: str
    rating: Optional[int] = None
    comment: Optional[str] = None
    user_query: Optional[str] = None
    assistant_message: Optional[str] = None
    page_url: Optional[str] = None
    created_at: str
    conversation_length: Optional[int] = None


class FeedbackListResponse(BaseModel):
    """Paginated list of feedbacks"""
    feedbacks: List[FeedbackListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: Dict[str, Any]


class FeedbackDetailConversation(BaseModel):
    """Conversation message in feedback detail"""
    role: str
    content: str
    message_order: int
    message_id: Optional[str] = None


class FeedbackDetailResponse(BaseModel):
    """Full feedback details with conversation"""
    id: int
    session_id: str
    feedback_type: str
    rating: Optional[int] = None
    comment: Optional[str] = None
    message_id: Optional[str] = None
    user_query: Optional[str] = None
    assistant_message: Optional[str] = None
    page_url: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: str
    conversation: List[FeedbackDetailConversation]


class FeedbackDashboardStats(BaseModel):
    """Dashboard statistics"""
    total_feedback: int
    thumbs_up_count: int
    thumbs_down_count: int
    rating_count: int
    comment_count: int
    avg_rating: Optional[float] = None
    satisfaction_rate: Optional[float] = None  # thumbs_up / (thumbs_up + thumbs_down) * 100
    period_days: int


class FeedbackDailyStats(BaseModel):
    """Daily feedback statistics"""
    date: str
    thumbs_up: int = 0
    thumbs_down: int = 0
    rating: int = 0
    comment: int = 0
    total: int = 0
    avg_rating: Optional[float] = None


class FeedbackTimeSeriesResponse(BaseModel):
    """Time series data for charts"""
    data: List[FeedbackDailyStats]
    period_days: int
    start_date: str
    end_date: str


class FeedbackTopPagesResponse(BaseModel):
    """Top pages with feedback"""
    pages: List[Dict[str, Any]]
    period_days: int


class SessionFeedbackResponse(BaseModel):
    """All feedback from a specific session"""
    session_id: str
    feedbacks: List[FeedbackDetailResponse]
    total: int


class FeedbackExportResponse(BaseModel):
    """Export response with data"""
    format: str
    total_records: int
    data: List[Dict[str, Any]]


# ============================================================================
# VOICE CHAT MODELS
# ============================================================================

class VoiceTokenRequest(BaseModel):
    """Request model for voice chat token generation"""
    session_id: str = Field(..., description="Unique session identifier")
    participant_name: Optional[str] = Field(None, description="Display name for participant")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user_123",
                "participant_name": "John Doe"
            }
        }


class VoiceTokenResponse(BaseModel):
    """Response model for voice chat token"""
    access_token: str = Field(..., description="LiveKit JWT access token")
    livekit_url: str = Field(..., description="LiveKit server WebSocket URL")
    room_name: str = Field(..., description="Room name to join")
    participant_identity: str = Field(..., description="Participant identity")

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "livekit_url": "wss://your-project.livekit.cloud",
                "room_name": "voice_user_123",
                "participant_identity": "user_123"
            }
        }


class VoiceMessageRequest(BaseModel):
    """Request model for voice message processing"""
    session_id: str = Field(..., description="Session identifier")
    audio_data: str = Field(..., description="Base64 encoded audio data")
    audio_format: Optional[str] = Field("webm", description="Audio format (webm, mp3, wav)")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user_123",
                "audio_data": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA...",
                "audio_format": "webm"
            }
        }


class VoiceMessageResponse(BaseModel):
    """Response model for voice message processing"""
    transcript: str = Field(..., description="Transcribed user speech")
    response_text: str = Field(..., description="Bot's text response")
    audio_data: str = Field(..., description="Base64 encoded audio response")
    audio_format: str = Field(..., description="Audio format of response")
    processing_time: float = Field(..., description="Processing time in seconds")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "transcript": "What is Export Genius?",
                "response_text": "Export Genius is a global trade intelligence platform...",
                "audio_data": "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2Z...",
                "audio_format": "mp3",
                "processing_time": 3.45,
                "metadata": {
                    "sources_used": ["Knowledge Base"],
                    "credits_remaining": 47
                }
            }
        }


class VoiceSessionStats(BaseModel):
    """Voice chat session statistics"""
    session_id: str
    room_name: str
    started_at: str
    message_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user_123",
                "room_name": "voice_user_123",
                "started_at": "2025-02-12T10:30:00Z",
                "message_count": 5
            }
        }


# ============================================================================
# Twilio Callback Models
# ============================================================================

class CallbackRequest(BaseModel):
    """Request model for phone callback feature"""
    session_id: str = Field(..., description="Session identifier")
    phone_number: str = Field(..., description="User's phone number (E.164 format)")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user_123",
                "phone_number": "+19876543210"
            }
        }


class CallbackResponse(BaseModel):
    """Response model for callback request"""
    status: str = Field(..., description="Call status (connecting, connected, failed)")
    message: str = Field(..., description="Status message")
    conference_name: Optional[str] = Field(None, description="Conference room name")
    user_call_sid: Optional[str] = Field(None, description="User's call SID")
    team_call_sid: Optional[str] = Field(None, description="Team's call SID")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "connecting",
                "message": "You'll receive a call shortly",
                "conference_name": "support-user_123",
                "user_call_sid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "team_call_sid": "CAyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
            }
        }


class CallStatusUpdate(BaseModel):
    """Webhook payload for call status updates"""
    CallSid: str
    CallStatus: str
    From: Optional[str] = None
    To: Optional[str] = None
    Direction: Optional[str] = None
    Duration: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "CallSid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "CallStatus": "completed",
                "From": "+19876543210",
                "To": "+12345678900",
                "Direction": "outbound-api",
                "Duration": "120"
            }
        }


# ============================================================================
# Twilio Callback Models
# ============================================================================

class CallbackRequest(BaseModel):
    """Request model for phone callback feature"""
    session_id: str = Field(..., description="Session identifier")
    phone_number: str = Field(..., description="User's phone number (E.164 format)")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user_123",
                "phone_number": "+19876543210"
            }
        }


class CallbackResponse(BaseModel):
    """Response model for callback request"""
    status: str = Field(..., description="Call status (connecting, connected, failed)")
    message: str = Field(..., description="Status message")
    conference_name: Optional[str] = Field(None, description="Conference room name")
    user_call_sid: Optional[str] = Field(None, description="User's call SID")
    team_call_sid: Optional[str] = Field(None, description="Team's call SID")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "connecting",
                "message": "You'll receive a call shortly",
                "conference_name": "support-user_123",
                "user_call_sid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "team_call_sid": "CAyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
            }
        }


class CallStatusUpdate(BaseModel):
    """Webhook payload for call status updates"""
    CallSid: str
    CallStatus: str
    From: Optional[str] = None
    To: Optional[str] = None
    Direction: Optional[str] = None
    Duration: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "CallSid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "CallStatus": "completed",
                "From": "+19876543210",
                "To": "+12345678900",
                "Direction": "outbound-api",
                "Duration": "120"
            }
        }


class OdooContextRequest(BaseModel):
    """Request model for sending chatbot history to Odoo"""
    session_id: str = Field(..., description="Unique session identifier for the chatbot session")
    guest_token: Optional[str] = Field(None, description="Odoo guest token from get_session response")
    channel_id: Optional[int] = Field(None, description="Odoo discuss.channel id from get_session response")
# ============================================================================
# Twilio Callback Models
# ============================================================================

class CallbackRequest(BaseModel):
    """Request model for phone callback feature"""
    session_id: str = Field(..., description="Session identifier")
    phone_number: str = Field(..., description="User's phone number (E.164 format)")

class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "guest_token": "8|c9f18fc2-5568-4482-a8b5-430a94b80c75",
                "channel_id": 18
                # "session_id": "user_123",
                # "phone_number": "+19876543210"
            }
        }


class OdooContextResponse(BaseModel):
    """Response model for sending chatbot history to Odoo"""
    success: bool = Field(..., description="Whether context was successfully sent to Odoo")
    message: str = Field(..., description="Status message")
    history_sent: bool = Field(..., description="Whether conversation history was sent")
    message_count: int = Field(..., description="Number of messages in history")
    odoo_channel_id: Optional[int] = Field(None, description="Odoo channel ID for the chat")
    error: Optional[str] = Field(None, description="Error message if sending failed")

class CallbackResponse(BaseModel):
    """Response model for callback request"""
    status: str = Field(..., description="Call status (connecting, connected, failed)")
    message: str = Field(..., description="Status message")
    conference_name: Optional[str] = Field(None, description="Conference room name")
    user_call_sid: Optional[str] = Field(None, description="User's call SID")
    team_call_sid: Optional[str] = Field(None, description="Team's call SID")

class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Context sent to Odoo successfully",
                "history_sent": True,
                "message_count": 5,
                "odoo_channel_id": 17,
                "error": None
            }
        }
        # for voice note
        #         "status": "connecting",
        #         "message": "You'll receive a call shortly",
        #         "conference_name": "support-user_123",
        #         "user_call_sid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        #         "team_call_sid": "CAyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
        #     }
        # }

class CallStatusUpdate(BaseModel):
    """Webhook payload for call status updates"""
    CallSid: str
    CallStatus: str
    From: Optional[str] = None
    To: Optional[str] = None
    Direction: Optional[str] = None
    Duration: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "CallSid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "CallStatus": "completed",
                "From": "+19876543210",
                "To": "+12345678900",
                "Direction": "outbound-api",
                "Duration": "120"
            }
        }


class OdooContextRequest(BaseModel):
    """Request model for sending chatbot history to Odoo"""
    session_id: str = Field(..., description="Unique session identifier for the chatbot session")
    guest_token: Optional[str] = Field(None, description="Odoo guest token from get_session response")
    channel_id: Optional[int] = Field(None, description="Odoo discuss.channel id from get_session response")

class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "guest_token": "8|c9f18fc2-5568-4482-a8b5-430a94b80c75",
                "channel_id": 18
            }
        }


class OdooContextResponse(BaseModel):
    """Response model for sending chatbot history to Odoo"""
    success: bool = Field(..., description="Whether context was successfully sent to Odoo")
    message: str = Field(..., description="Status message")
    history_sent: bool = Field(..., description="Whether conversation history was sent")
    message_count: int = Field(..., description="Number of messages in history")
    odoo_channel_id: Optional[int] = Field(None, description="Odoo channel ID for the chat")
    error: Optional[str] = Field(None, description="Error message if sending failed")

class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Context sent to Odoo successfully",
                "history_sent": True,
                "message_count": 5,
                "odoo_channel_id": 17,
                "error": None
            }
        }



class OdooContextRequest(BaseModel):
    """Request model for sending chatbot history to Odoo"""
    session_id: str = Field(..., description="Unique session identifier for the chatbot session")
    guest_token: Optional[str] = Field(None, description="Odoo guest token from get_session response")
    channel_id: Optional[int] = Field(None, description="Odoo discuss.channel id from get_session response")
# ============================================================================
# Twilio Callback Models
# ============================================================================

class CallbackRequest(BaseModel):
    """Request model for phone callback feature"""
    session_id: str = Field(..., description="Session identifier")
    phone_number: str = Field(..., description="User's phone number (E.164 format)")

class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "guest_token": "8|c9f18fc2-5568-4482-a8b5-430a94b80c75",
                "channel_id": 18
                # "session_id": "user_123",
                # "phone_number": "+19876543210"
            }
        }


class OdooContextResponse(BaseModel):
    """Response model for sending chatbot history to Odoo"""
    success: bool = Field(..., description="Whether context was successfully sent to Odoo")
    message: str = Field(..., description="Status message")
    history_sent: bool = Field(..., description="Whether conversation history was sent")
    message_count: int = Field(..., description="Number of messages in history")
    odoo_channel_id: Optional[int] = Field(None, description="Odoo channel ID for the chat")
    error: Optional[str] = Field(None, description="Error message if sending failed")

class CallbackResponse(BaseModel):
    """Response model for callback request"""
    status: str = Field(..., description="Call status (connecting, connected, failed)")
    message: str = Field(..., description="Status message")
    conference_name: Optional[str] = Field(None, description="Conference room name")
    user_call_sid: Optional[str] = Field(None, description="User's call SID")
    team_call_sid: Optional[str] = Field(None, description="Team's call SID")

class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Context sent to Odoo successfully",
                "history_sent": True,
                "message_count": 5,
                "odoo_channel_id": 17,
                "error": None
            }
        }
        # for voice note
        #         "status": "connecting",
        #         "message": "You'll receive a call shortly",
        #         "conference_name": "support-user_123",
        #         "user_call_sid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        #         "team_call_sid": "CAyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
        #     }
        # }

class CallStatusUpdate(BaseModel):
    """Webhook payload for call status updates"""
    CallSid: str
    CallStatus: str
    From: Optional[str] = None
    To: Optional[str] = None
    Direction: Optional[str] = None
    Duration: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "CallSid": "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "CallStatus": "completed",
                "From": "+19876543210",
                "To": "+12345678900",
                "Direction": "outbound-api",
                "Duration": "120"
            }
        }


class OdooContextRequest(BaseModel):
    """Request model for sending chatbot history to Odoo"""
    session_id: str = Field(..., description="Unique session identifier for the chatbot session")
    guest_token: Optional[str] = Field(None, description="Odoo guest token from get_session response")
    channel_id: Optional[int] = Field(None, description="Odoo discuss.channel id from get_session response")

class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "guest_token": "8|c9f18fc2-5568-4482-a8b5-430a94b80c75",
                "channel_id": 18
            }
        }


class OdooContextResponse(BaseModel):
    """Response model for sending chatbot history to Odoo"""
    success: bool = Field(..., description="Whether context was successfully sent to Odoo")
    message: str = Field(..., description="Status message")
    history_sent: bool = Field(..., description="Whether conversation history was sent")
    message_count: int = Field(..., description="Number of messages in history")
    odoo_channel_id: Optional[int] = Field(None, description="Odoo channel ID for the chat")
    error: Optional[str] = Field(None, description="Error message if sending failed")

class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Context sent to Odoo successfully",
                "history_sent": True,
                "message_count": 5,
                "odoo_channel_id": 17,
                "error": None
            }
        }