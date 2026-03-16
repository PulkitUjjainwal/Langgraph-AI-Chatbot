"""
User Information Collection Models

Data models for the natural user information collection system:
- UserInfoState: In-memory state management
- Request/Response models for API endpoints
- Analytics and statistics models
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class UserInfoField(str, Enum):
    """Enum for user info fields"""
    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    REQUIREMENTS = "requirements"


class CollectionPhase(str, Enum):
    """Current collection phase"""
    NOT_STARTED = "not_started"
    COLLECTING_NAME = "collecting_name"
    COLLECTING_EMAIL = "collecting_email"
    COLLECTING_PHONE = "collecting_phone"
    COLLECTING_REQUIREMENTS = "collecting_requirements"
    PAUSED = "paused"
    COMPLETED = "completed"


# ============================================================================
# DATACLASSES (for internal state management)
# ============================================================================

@dataclass
class UserInfoState:
    """
    Internal state for user information collection.
    Stored in Redis for fast access during conversation.
    """
    session_id: str

    # Collected fields
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    requirements: Optional[Dict[str, Any]] = None  # Structured requirements

    # Progress tracking
    completion_percentage: float = 0.0
    fields_collected: List[str] = field(default_factory=list)

    # Collection metadata
    name_ask_count: int = 0
    email_ask_count: int = 0
    phone_ask_count: int = 0
    requirements_ask_count: int = 0

    # Resistance handling
    collection_paused: bool = False
    last_field_asked: Optional[str] = None
    last_ask_at: Optional[datetime] = None
    pause_until_message_count: Optional[int] = None
    current_message_count: int = 0

    # Phase tracking
    current_phase: CollectionPhase = CollectionPhase.NOT_STARTED

    # Timestamps
    first_field_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis storage"""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "requirements": self.requirements,
            "completion_percentage": self.completion_percentage,
            "fields_collected": self.fields_collected,
            "name_ask_count": self.name_ask_count,
            "email_ask_count": self.email_ask_count,
            "phone_ask_count": self.phone_ask_count,
            "requirements_ask_count": self.requirements_ask_count,
            "collection_paused": self.collection_paused,
            "last_field_asked": self.last_field_asked,
            "last_ask_at": self.last_ask_at.isoformat() if self.last_ask_at else None,
            "pause_until_message_count": self.pause_until_message_count,
            "current_message_count": self.current_message_count,
            "current_phase": self.current_phase.value if isinstance(self.current_phase, CollectionPhase) else self.current_phase,
            "first_field_at": self.first_field_at.isoformat() if self.first_field_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserInfoState':
        """Create UserInfoState from dictionary (Redis retrieval)"""
        # Parse datetime fields
        for field_name in ['last_ask_at', 'first_field_at', 'completed_at', 'created_at', 'updated_at']:
            if data.get(field_name):
                if isinstance(data[field_name], str):
                    data[field_name] = datetime.fromisoformat(data[field_name])

        # Parse enum
        if data.get('current_phase'):
            if isinstance(data['current_phase'], str):
                data['current_phase'] = CollectionPhase(data['current_phase'])

        return cls(**data)


# ============================================================================
# COLLECTION DECISION MODELS
# ============================================================================

@dataclass
class CollectionDecision:
    """Decision about whether to collect user info in current turn"""
    should_collect: bool
    field_to_collect: Optional[UserInfoField] = None
    prompt_message: Optional[str] = None
    collection_weight: float = 0.0  # 0.0 to 1.0, affects response generation
    reason: Optional[str] = None


# ============================================================================
# API REQUEST/RESPONSE MODELS
# ============================================================================

class SaveUserInfoRequest(BaseModel):
    """Request model for saving user info"""
    session_id: str = Field(..., description="Session identifier")
    field: UserInfoField = Field(..., description="Field being saved")
    value: str = Field(..., description="Field value")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "field": "name",
                "value": "John Doe"
            }
        }


class SaveUserInfoResponse(BaseModel):
    """Response model for save user info endpoint"""
    success: bool = Field(..., description="Whether info was saved successfully")
    session_id: str = Field(..., description="Session identifier")
    field: str = Field(..., description="Field that was saved")
    completion_percentage: float = Field(..., description="Updated completion percentage (0.0 to 1.0)")
    fields_collected: List[str] = Field(..., description="List of all collected fields")
    message: str = Field(..., description="Response message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "session_id": "user123",
                "field": "name",
                "completion_percentage": 0.3,
                "fields_collected": ["name"],
                "message": "Name saved successfully"
            }
        }


class GetUserInfoRequest(BaseModel):
    """Request model for getting user info"""
    session_id: str = Field(..., description="Session identifier")


class GetUserInfoResponse(BaseModel):
    """Response model for get user info endpoint"""
    session_id: str = Field(..., description="Session identifier")
    name: Optional[str] = Field(None, description="User name")
    email: Optional[str] = Field(None, description="User email")
    phone: Optional[str] = Field(None, description="User phone")
    requirements: Optional[Dict[str, Any]] = Field(None, description="User requirements")
    completion_percentage: float = Field(..., description="Completion percentage (0.0 to 1.0)")
    fields_collected: List[str] = Field(..., description="List of collected fields")
    collection_paused: bool = Field(..., description="Whether collection is paused")
    current_phase: str = Field(..., description="Current collection phase")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "+1234567890",
                "requirements": {
                    "use_case": "trade_intelligence",
                    "industry": "manufacturing",
                    "company_size": "medium"
                },
                "completion_percentage": 1.0,
                "fields_collected": ["name", "email", "phone", "requirements"],
                "collection_paused": False,
                "current_phase": "completed"
            }
        }


class PauseCollectionRequest(BaseModel):
    """Request model for pausing collection"""
    session_id: str = Field(..., description="Session identifier")
    pause_for_messages: int = Field(5, description="Pause for N messages", ge=1, le=20)

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "user123",
                "pause_for_messages": 5
            }
        }


class PauseCollectionResponse(BaseModel):
    """Response model for pause collection endpoint"""
    success: bool = Field(..., description="Whether collection was paused")
    session_id: str = Field(..., description="Session identifier")
    paused_until_message_count: int = Field(..., description="Message count when collection will resume")
    message: str = Field(..., description="Response message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "session_id": "user123",
                "paused_until_message_count": 15,
                "message": "Collection paused for 5 messages"
            }
        }


class UserInfoStatsResponse(BaseModel):
    """Response model for user info statistics"""
    total_sessions_with_info: int = Field(..., description="Total sessions with any info")
    sessions_with_name: int = Field(..., description="Sessions with name collected")
    sessions_with_email: int = Field(..., description="Sessions with email collected")
    sessions_with_phone: int = Field(..., description="Sessions with phone collected")
    sessions_with_requirements: int = Field(..., description="Sessions with requirements collected")
    avg_completion_percentage: float = Field(..., description="Average completion percentage")
    sessions_60_plus_complete: int = Field(..., description="Sessions with 60%+ completion")
    sessions_with_resistance: int = Field(..., description="Sessions where collection was paused")
    avg_name_asks: float = Field(..., description="Average asks before name collected")
    avg_email_asks: float = Field(..., description="Average asks before email collected")
    avg_phone_asks: float = Field(..., description="Average asks before phone collected")
    period_days: int = Field(..., description="Period in days")

    class Config:
        json_schema_extra = {
            "example": {
                "total_sessions_with_info": 850,
                "sessions_with_name": 520,
                "sessions_with_email": 340,
                "sessions_with_phone": 170,
                "sessions_with_requirements": 280,
                "avg_completion_percentage": 0.48,
                "sessions_60_plus_complete": 310,
                "sessions_with_resistance": 125,
                "avg_name_asks": 1.2,
                "avg_email_asks": 1.8,
                "avg_phone_asks": 2.1,
                "period_days": 30
            }
        }


class DailyCollectionMetrics(BaseModel):
    """Daily collection metrics"""
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    sessions_with_collection: int = Field(..., description="Sessions with collection attempted")
    name_collected: int = Field(..., description="Names collected")
    email_collected: int = Field(..., description="Emails collected")
    phone_collected: int = Field(..., description="Phones collected")
    avg_completion: float = Field(..., description="Average completion percentage")
    resistance_count: int = Field(..., description="Number of resistance events")
    total_sessions: int = Field(..., description="Total sessions for the day")
    collection_attempt_rate: float = Field(..., description="Percentage of sessions with collection attempt")


class CollectionTimeSeriesResponse(BaseModel):
    """Time series data for collection analytics"""
    data: List[DailyCollectionMetrics] = Field(..., description="Daily metrics")
    period_days: int = Field(..., description="Period in days")
    start_date: str = Field(..., description="Start date")
    end_date: str = Field(..., description="End date")


class CollectionFunnelItem(BaseModel):
    """Single funnel stage"""
    stage: str = Field(..., description="Funnel stage name")
    count: int = Field(..., description="Number of sessions")
    percentage: float = Field(..., description="Percentage of total sessions")


class CollectionFunnelResponse(BaseModel):
    """Collection funnel analysis"""
    funnel: List[CollectionFunnelItem] = Field(..., description="Funnel stages")
    period_days: int = Field(..., description="Period in days")

    class Config:
        json_schema_extra = {
            "example": {
                "funnel": [
                    {"stage": "Total Sessions", "count": 1000, "percentage": 100.0},
                    {"stage": "Collection Attempted", "count": 850, "percentage": 85.0},
                    {"stage": "Name Collected", "count": 520, "percentage": 52.0},
                    {"stage": "Email Collected", "count": 340, "percentage": 34.0},
                    {"stage": "Phone Collected", "count": 170, "percentage": 17.0}
                ],
                "period_days": 30
            }
        }


class UserInfoListItem(BaseModel):
    """Single user info item for list view"""
    id: int
    session_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    completion_percentage: float
    fields_collected: List[str]
    collection_paused: bool
    created_at: str
    updated_at: str


class UserInfoListResponse(BaseModel):
    """Paginated list of user info"""
    user_infos: List[UserInfoListItem]
    total: int
    limit: int
    offset: int
    has_more: bool


# ============================================================================
# EXTRACTION RESULT MODEL
# ============================================================================

@dataclass
class ExtractionResult:
    """Result of extracting info from user message"""
    field: UserInfoField
    value: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0
    extracted: bool = False
    method: Optional[str] = None  # "regex", "keyword", "llm", etc.
