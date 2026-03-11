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

    # Device & Browser Information
    device_type: Optional[str] = Field(None, description="Device type: mobile, tablet, desktop")
    browser_name: Optional[str] = Field(None, description="Browser name")
    browser_version: Optional[str] = Field(None, description="Browser version")
    os_name: Optional[str] = Field(None, description="Operating system name")
    os_version: Optional[str] = Field(None, description="Operating system version")

    # Language & Timezone
    timezone: Optional[str] = Field(None, description="User timezone")
    language: Optional[str] = Field(None, description="Browser language preference")

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
# SUPPORT INTERACTION MODELS (Click Tracking & Analytics)
# ============================================================================

from enum import Enum

class SupportInteractionType(str, Enum):
    """Enum for support interaction types"""
    MODE_SWITCH = "mode_switch"                  # User switched between General/Company mode
    SUGGESTED_QUESTION = "suggested_question"     # User clicked a suggested question chip
    URL_INPUT = "url_input"                       # User entered/submitted Export Genius URL
    LEAD_CAPTURE = "lead_capture"                 # User submitted lead capture form
    ODOO_ESCALATION = "odoo_escalation"          # User requested Odoo CRM escalation
    TWILIO_CALLBACK = "twilio_callback"           # User requested phone callback
    VOICE_CHAT_START = "voice_chat_start"         # User started voice chat
    VOICE_CHAT_END = "voice_chat_end"             # User ended voice chat
    FILE_UPLOAD = "file_upload"                   # User uploaded a file
    EXPORT_DATA = "export_data"                   # User exported conversation/data
    SHARE_CONVERSATION = "share_conversation"     # User shared conversation
    CLEAR_CONVERSATION = "clear_conversation"     # User cleared/reset conversation
    FEEDBACK_GIVEN = "feedback_given"             # User gave feedback
    COPY_MESSAGE = "copy_message"                 # User copied assistant message
    REGENERATE_RESPONSE = "regenerate_response"   # User requested response regeneration
    WHATSAPP_REQUEST = "whatsapp_request"         # User clicked WhatsApp button (QR or link)
    SCHEDULE_DEMO = "schedule_demo"               # User clicked schedule demo button
    CHAT_WITH_US = "chat_with_us"                 # User clicked chat with us button
    CALL_REQUEST = "call_request"                 # User clicked call request button
    QUESTION_CARD_CLICK = "question_card_click"   # User clicked question card
    DATA_TYPE_SELECTION = "data_type_selection"   # User selected data type (Import/Export/Both)
    COUNTRY_INPUT = "country_input"               # User entered country
    PRODUCT_INPUT = "product_input"               # User entered product
    OTHER = "other"                               # Other custom interactions


class ConversionType(str, Enum):
    """Enum for conversion types"""
    LEAD = "lead"
    CALLBACK = "callback"
    ESCALATION = "escalation"
    NONE = "none"


class SupportInteractionRequest(BaseModel):
    """Request model for tracking support interaction"""
    session_id: str = Field(..., description="Session identifier")
    interaction_type: SupportInteractionType = Field(..., description="Type of support interaction")
    interaction_data: Optional[Dict[str, Any]] = Field(None, description="Additional structured data about the interaction")
    page_url: Optional[str] = Field(None, description="Page URL where interaction occurred")
    message_context: Optional[str] = Field(None, description="Related message content if applicable")
    interaction_order: Optional[int] = Field(None, description="Order of this interaction in the session")
    led_to_conversion: bool = Field(False, description="Did this lead to a conversion?")
    conversion_type: ConversionType = Field(ConversionType.NONE, description="Type of conversion if applicable")

    # Device & Browser Information
    device_type: Optional[str] = Field(None, description="Device type: mobile, tablet, desktop")
    browser_name: Optional[str] = Field(None, description="Browser name")
    os_name: Optional[str] = Field(None, description="Operating system")

    # Location
    country: Optional[str] = Field(None, description="Country from IP")
    region: Optional[str] = Field(None, description="Region/State")
    city: Optional[str] = Field(None, description="City")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123_session_xyz",
                "interaction_type": "suggested_question",
                "interaction_data": {
                    "question": "What is Export Genius?",
                    "index": 0,
                    "question_category": "general"
                },
                "page_url": "https://www.exportgenius.in/",
                "message_context": "User selected first suggested question",
                "interaction_order": 1,
                "led_to_conversion": False,
                "conversion_type": "none",
                "device_type": "desktop",
                "browser_name": "Chrome",
                "os_name": "Windows",
                "country": "United States",
                "region": "California",
                "city": "San Francisco"
            }
        }


class SupportInteractionResponse(BaseModel):
    """Response model for support interaction tracking"""
    success: bool = Field(..., description="Whether interaction was tracked successfully")
    interaction_id: Optional[int] = Field(None, description="Database ID of the stored interaction")
    message: str = Field(..., description="Response message")
    storage: Optional[str] = Field(None, description="Storage type: 'mysql' or 'file'")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "interaction_id": 12345,
                "message": "Support interaction tracked successfully",
                "storage": "mysql"
            }
        }


class SupportInteractionItem(BaseModel):
    """Single support interaction for display"""
    id: int
    session_id: str
    interaction_type: str
    interaction_data: Optional[Dict[str, Any]] = None
    page_url: Optional[str] = None
    message_context: Optional[str] = None
    interaction_order: Optional[int] = None
    led_to_conversion: bool
    conversion_type: str
    device_type: Optional[str] = None
    country: Optional[str] = None
    created_at: str


class SessionInteractionsResponse(BaseModel):
    """All support interactions for a specific session"""
    session_id: str
    interactions: List[SupportInteractionItem]
    total: int


class SupportOptionStats(BaseModel):
    """Statistics for a specific support option"""
    interaction_type: str
    total_clicks: int
    unique_users: int
    total_conversions: int
    conversion_rate_pct: float
    avg_interaction_order: Optional[float] = None
    countries_reached: int


class SupportAnalyticsResponse(BaseModel):
    """Analytics data for support options usage"""
    period_days: int
    total_interactions: int
    total_unique_sessions: int
    overall_conversion_rate: float

    # Most popular support options
    popular_options: List[SupportOptionStats]

    # Breakdown by type
    interactions_by_type: Dict[str, int]

    # Device breakdown
    interactions_by_device: Dict[str, int]

    # Geographic breakdown (top countries)
    interactions_by_country: List[Dict[str, Any]]

    # Conversion metrics
    total_conversions: int
    conversions_by_type: Dict[str, int]

    class Config:
        json_schema_extra = {
            "example": {
                "period_days": 30,
                "total_interactions": 5420,
                "total_unique_sessions": 1890,
                "overall_conversion_rate": 12.5,
                "popular_options": [
                    {
                        "interaction_type": "suggested_question",
                        "total_clicks": 2100,
                        "unique_users": 980,
                        "total_conversions": 145,
                        "conversion_rate_pct": 6.9,
                        "avg_interaction_order": 1.2,
                        "countries_reached": 45
                    },
                    {
                        "interaction_type": "mode_switch",
                        "total_clicks": 1560,
                        "unique_users": 780,
                        "total_conversions": 89,
                        "conversion_rate_pct": 5.7,
                        "avg_interaction_order": 2.1,
                        "countries_reached": 38
                    }
                ],
                "interactions_by_type": {
                    "suggested_question": 2100,
                    "mode_switch": 1560,
                    "url_input": 890,
                    "lead_capture": 320,
                    "voice_chat_start": 245
                },
                "interactions_by_device": {
                    "desktop": 3200,
                    "mobile": 1890,
                    "tablet": 330
                },
                "interactions_by_country": [
                    {"country": "United States", "count": 1890, "conversions": 145},
                    {"country": "India", "count": 1230, "conversions": 89},
                    {"country": "United Kingdom", "count": 670, "conversions": 45}
                ],
                "total_conversions": 679,
                "conversions_by_type": {
                    "lead": 320,
                    "callback": 189,
                    "escalation": 170
                }
            }
        }


class SupportDailyStats(BaseModel):
    """Daily support interaction statistics"""
    date: str
    interaction_type: str
    interaction_count: int
    unique_sessions: int
    conversions: int
    conversion_rate_pct: float
    mobile_users: int
    desktop_users: int
    tablet_users: int


class SupportTimeSeriesResponse(BaseModel):
    """Time series data for support analytics charts"""
    data: List[SupportDailyStats]
    period_days: int
    start_date: str
    end_date: str

    class Config:
        json_schema_extra = {
            "example": {
                "data": [
                    {
                        "date": "2025-12-01",
                        "interaction_type": "suggested_question",
                        "interaction_count": 145,
                        "unique_sessions": 67,
                        "conversions": 8,
                        "conversion_rate_pct": 5.5,
                        "mobile_users": 32,
                        "desktop_users": 29,
                        "tablet_users": 6
                    }
                ],
                "period_days": 30,
                "start_date": "2025-11-01",
                "end_date": "2025-12-01"
            }
        }


class DeviceSupportPreference(BaseModel):
    """Support preference by device type"""
    device_type: str
    interaction_type: str
    usage_count: int
    unique_sessions: int
    pct_of_device_interactions: float


class DeviceSupportPreferencesResponse(BaseModel):
    """Device-based support preferences"""
    preferences: List[DeviceSupportPreference]
    period_days: int


class ConversionFunnelItem(BaseModel):
    """Single conversion funnel entry"""
    session_id: str
    started_at: str
    message_count: int
    unique_interactions_used: int
    interaction_path: str
    converted: bool
    conversion_type: str
    device_type: Optional[str] = None
    country: Optional[str] = None


class ConversionFunnelResponse(BaseModel):
    """Conversion funnel analysis"""
    funnel_items: List[ConversionFunnelItem]
    total_converted_sessions: int
    avg_interactions_to_convert: float
    most_common_path: str
    period_days: int


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

# ============================================================================
# CONVERSATION HISTORY MODELS
# ============================================================================

class SaveConversationRequest(BaseModel):
    """Request model for saving conversation history"""
    session_id: str = Field(..., description="Session identifier")
    initial_url: Optional[str] = Field(None, description="Initial page URL where chat started")
    page_urls: Optional[List[str]] = Field(None, description="List of all pages visited during session")
    user_agent: Optional[str] = Field(None, description="Browser user agent")
    ip_address: Optional[str] = Field(None, description="User IP address")
    has_feedback: Optional[bool] = Field(False, description="Whether user provided feedback")
    lead_captured: Optional[bool] = Field(False, description="Whether lead was captured")

    # Device & Browser Information
    device_type: Optional[str] = Field(None, description="Device type: mobile, tablet, desktop")
    browser_name: Optional[str] = Field(None, description="Browser name")
    browser_version: Optional[str] = Field(None, description="Browser version")
    os_name: Optional[str] = Field(None, description="Operating system name")
    os_version: Optional[str] = Field(None, description="Operating system version")

    # Language & Timezone
    timezone: Optional[str] = Field(None, description="User timezone")
    language: Optional[str] = Field(None, description="Browser language preference")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "initial_url": "https://marketinsidedata.com/",
                "page_urls": [
                    "https://marketinsidedata.com/",
                    "https://marketinsidedata.com/about"
                ],
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                "ip_address": "192.168.1.1",
                "has_feedback": False,
                "lead_captured": False,
                "device_type": "desktop",
                "browser_name": "Chrome",
                "browser_version": "120.0.0.0",
                "os_name": "Windows",
                "os_version": "10",
                "timezone": "America/New_York",
                "language": "en-US"
            }
        }


class SaveConversationResponse(BaseModel):
    """Response model for save conversation endpoint"""
    success: bool = Field(..., description="Whether conversation was saved successfully")
    session_id: str = Field(..., description="Session identifier")
    message_count: int = Field(..., description="Number of messages saved")
    storage: Optional[str] = Field(None, description="Storage type: 'mysql' or 'file'")
    message: str = Field(..., description="Response message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "session_id": "user123",
                "message_count": 12,
                "storage": "mysql",
                "message": "Conversation history saved successfully"
            }
        }


class ConversationStatsResponse(BaseModel):
    """Response model for conversation statistics"""
    period_days: int = Field(..., description="Number of days in the stats period")
    total_sessions: int = Field(..., description="Total number of sessions")
    total_messages: int = Field(..., description="Total number of messages")
    avg_messages_per_session: float = Field(..., description="Average messages per session")
    sessions_with_feedback: int = Field(..., description="Sessions with feedback")
    sessions_with_leads: int = Field(..., description="Sessions with leads captured")
    avg_duration_minutes: float = Field(..., description="Average session duration in minutes")

    class Config:
        json_schema_extra = {
            "example": {
                "period_days": 30,
                "total_sessions": 1500,
                "total_messages": 9000,
                "avg_messages_per_session": 6.0,
                "sessions_with_feedback": 450,
                "sessions_with_leads": 200,
                "avg_duration_minutes": 8.5
            }
        }
