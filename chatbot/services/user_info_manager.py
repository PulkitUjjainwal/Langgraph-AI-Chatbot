"""
User Information Manager

Natural, conversational user information collection system.
Progressive collection: name → email → phone → requirements.

Features:
- Progressive weighting (80/20 → 20/80 as fields collected)
- Natural prompt generation contextual to conversation
- Resistance detection and graceful fallback
- Field extraction from user messages
- Dual storage: Redis (fast access) + MySQL (persistence)
"""

import json
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from dataclasses import asdict

from chatbot.models.user_info_models import (
    UserInfoState,
    UserInfoField,
    CollectionPhase,
    CollectionDecision,
    ExtractionResult
)
from chatbot.database.user_info_service import UserInfoService
from chatbot.integrations.redis.client import RedisMemoryManager
from chatbot.utils.email_validator import get_email_validator


class UserInfoManager:
    """
    Manages natural user information collection during conversation.

    Collection Strategy:
    1. Start with 80% focus on collection, 20% on Q&A
    2. Gradually shift to 20% collection, 80% Q&A as fields are collected
    3. Never block answers - always respond to user's question first
    4. Detect resistance (ignore, refuse, topic change) and pause gracefully
    5. Resume collection after N messages if paused

    Field Priority:
    1. Name (30% completion weight)
    2. Email (30% completion weight)
    3. Phone (20% completion weight - optional)
    4. Requirements (20% completion weight)
    """

    # Field weights for completion percentage
    FIELD_WEIGHTS = {
        UserInfoField.NAME: 0.30,
        UserInfoField.EMAIL: 0.30,
        UserInfoField.PHONE: 0.20,
        UserInfoField.REQUIREMENTS: 0.20
    }

    # Collection timing
    MESSAGE_COUNT_NAME = 2  # Ask for name after message 2
    MESSAGE_COUNT_EMAIL = 2  # Ask for email 2 messages after name
    MESSAGE_COUNT_PHONE = 3  # Ask for phone 3 messages after email (optional)
    MESSAGE_COUNT_REQUIREMENTS = 2  # Ask for requirements 2 messages after email

    # Resistance thresholds
    MAX_ASK_COUNT = 3  # Maximum times to ask for same field
    PAUSE_MESSAGES = 5  # Pause for 5 messages after resistance detected

    def __init__(
        self,
        redis_manager: RedisMemoryManager,
        user_info_service: UserInfoService
    ):
        self.redis = redis_manager
        self.db_service = user_info_service
        self.email_validator = get_email_validator()

        # Track email validation attempts per session
        self._email_validation_attempts = {}  # {session_id: count}

    # ========================================================================
    # STATE MANAGEMENT
    # ========================================================================

    async def get_state(self, session_id: str) -> UserInfoState:
        """Get or create user info state for session"""
        # Try Redis first (fast)
        redis_key = f"user_info:{session_id}"
        redis_data = self.redis.client.get(redis_key)

        if redis_data:
            try:
                state_dict = json.loads(redis_data)
                return UserInfoState.from_dict(state_dict)
            except Exception as e:
                print(f"[UserInfoManager] Redis parse error: {e}")

        # Fallback to MySQL
        db_data = await self.db_service.get_user_info(session_id)
        if db_data:
            # Parse fields_declined JSON if it's a string
            fields_declined = db_data.get('fields_declined', [])
            if isinstance(fields_declined, str):
                try:
                    import json
                    fields_declined = json.loads(fields_declined)
                except:
                    fields_declined = []

            state = UserInfoState(
                session_id=session_id,
                name=db_data.get('name'),
                email=db_data.get('email'),
                phone=db_data.get('phone'),
                requirements=db_data.get('requirements'),
                completion_percentage=db_data.get('completion_percentage', 0.0),
                fields_collected=db_data.get('fields_collected', []),
                name_ask_count=db_data.get('name_ask_count', 0),
                email_ask_count=db_data.get('email_ask_count', 0),
                phone_ask_count=db_data.get('phone_ask_count', 0),
                requirements_ask_count=db_data.get('requirements_ask_count', 0),
                name_rejection_count=db_data.get('name_rejection_count', 0),
                email_rejection_count=db_data.get('email_rejection_count', 0),
                phone_rejection_count=db_data.get('phone_rejection_count', 0),
                requirements_rejection_count=db_data.get('requirements_rejection_count', 0),
                fields_declined=fields_declined,
                collection_paused=db_data.get('collection_paused', False),
                last_field_asked=db_data.get('last_field_asked'),
                pause_until_message_count=db_data.get('pause_until_message_count')
            )
            # Save to Redis for fast access
            self._save_state_to_redis(state)
            return state

        # Create new state
        state = UserInfoState(session_id=session_id)
        return state

    def _save_state_to_redis(self, state: UserInfoState):
        """Save state to Redis"""
        redis_key = f"user_info:{state.session_id}"
        state_dict = state.to_dict()
        self.redis.client.setex(
            redis_key,
            self.redis.ttl_seconds,
            json.dumps(state_dict, default=str)
        )

    async def _save_state_to_mysql(self, state: UserInfoState, field: str, value: str):
        """Save state to MySQL"""
        state_data = {
            'completion_percentage': state.completion_percentage,
            'fields_collected': state.fields_collected,
            f'{field}_ask_count': getattr(state, f'{field}_ask_count'),
            'collection_paused': state.collection_paused,
            'last_field_asked': state.last_field_asked,
            'pause_until_message_count': state.pause_until_message_count
        }

        await self.db_service.save_user_info(
            session_id=state.session_id,
            field=field,
            value=value,
            state_data=state_data
        )

    async def _save_rejection_to_mysql(self, state: UserInfoState, field: UserInfoField):
        """Save rejection count to MySQL"""
        import json
        rejection_data = {
            f'{field.value}_rejection_count': getattr(state, f'{field.value}_rejection_count'),
            'fields_declined': json.dumps(state.fields_declined) if state.fields_declined else None
        }

        # Use update_user_info to update just the rejection counts
        await self.db_service.update_user_info(
            session_id=state.session_id,
            updates=rejection_data
        )

        # Also save to Redis
        self._save_state_to_redis(state)

    # ========================================================================
    # COLLECTION DECISION
    # ========================================================================

    async def should_collect_info(
        self,
        session_id: str,
        message: str,
        message_count: int,
        detected_intent: Optional[str] = None
    ) -> CollectionDecision:
        """
        Decide whether to collect user info in this turn.

        Args:
            session_id: Session identifier
            message: User's message
            message_count: Total message count in session
            detected_intent: Detected user intent (e.g., "pricing_query", "demo_request")

        Returns:
            CollectionDecision with should_collect, field, prompt, weight
        """
        state = await self.get_state(session_id)

        # Update message count
        state.current_message_count = message_count

        # Check if collection is paused
        if state.collection_paused:
            if state.pause_until_message_count and message_count >= state.pause_until_message_count:
                # Resume collection
                state.collection_paused = False
                state.pause_until_message_count = None
                self._save_state_to_redis(state)
                print(f"[UserInfoManager] Resuming collection for {session_id}")
            else:
                # Still paused
                return CollectionDecision(
                    should_collect=False,
                    collection_weight=0.0,
                    reason="Collection paused due to resistance"
                )

        # Determine next field to collect
        field_to_collect = self._determine_next_field(state, message_count)

        if not field_to_collect:
            # All fields collected or no field is ready
            return CollectionDecision(
                should_collect=False,
                collection_weight=0.0,
                reason="All fields collected or timing not right"
            )

        # Check if we've asked too many times
        ask_count = self._get_ask_count(state, field_to_collect)
        if ask_count >= self.MAX_ASK_COUNT:
            print(f"[UserInfoManager] Max asks reached for {field_to_collect.value}")
            return CollectionDecision(
                should_collect=False,
                collection_weight=0.0,
                reason=f"Max ask count reached for {field_to_collect.value}"
            )

        # Calculate collection weight (0.0 to 1.0)
        weight = self._calculate_collection_weight(state)

        # Generate natural prompt
        prompt = self._generate_prompt(
            field=field_to_collect,
            message=message,
            detected_intent=detected_intent,
            ask_count=ask_count
        )

        # Update state
        state.last_field_asked = field_to_collect.value
        state.last_ask_at = datetime.now()
        self._increment_ask_count(state, field_to_collect)
        self._save_state_to_redis(state)

        return CollectionDecision(
            should_collect=True,
            field_to_collect=field_to_collect,
            prompt_message=prompt,
            collection_weight=weight,
            reason=f"Collecting {field_to_collect.value}"
        )

    def _determine_next_field(
        self,
        state: UserInfoState,
        message_count: int
    ) -> Optional[UserInfoField]:
        """
        Determine which field to collect next based on state and timing.
        SKIPS fields that have been permanently declined (4+ rejections).
        """
        # Priority 1: Name (if not collected, not declined, and timing is right)
        if not state.name and message_count >= self.MESSAGE_COUNT_NAME:
            if not self._is_field_declined(state, UserInfoField.NAME):
                return UserInfoField.NAME
            else:
                print(f"[UserInfoManager] ⏭️ Skipping 'name' - permanently declined")

        # Priority 2: Email (after name collected + wait period)
        if state.name and not state.email:
            if not self._is_field_declined(state, UserInfoField.EMAIL):
                name_field_index = state.fields_collected.index('name') if 'name' in state.fields_collected else -1
                if name_field_index >= 0:
                    messages_since_name = message_count - (name_field_index * 2 + self.MESSAGE_COUNT_NAME)
                    if messages_since_name >= self.MESSAGE_COUNT_EMAIL:
                        return UserInfoField.EMAIL
            else:
                print(f"[UserInfoManager] ⏭️ Skipping 'email' - permanently declined")

        # Priority 3: Requirements (after email, optional before phone)
        if state.email and not state.requirements:
            if not self._is_field_declined(state, UserInfoField.REQUIREMENTS):
                email_field_index = state.fields_collected.index('email') if 'email' in state.fields_collected else -1
                if email_field_index >= 0:
                    messages_since_email = message_count - len(state.fields_collected) * 2
                    if messages_since_email >= self.MESSAGE_COUNT_REQUIREMENTS:
                        return UserInfoField.REQUIREMENTS
            else:
                print(f"[UserInfoManager] ⏭️ Skipping 'requirements' - permanently declined")

        # Priority 4: Phone (optional, only if email exists and context is right)
        if state.email and not state.phone:
            if not self._is_field_declined(state, UserInfoField.PHONE):
                email_field_index = state.fields_collected.index('email') if 'email' in state.fields_collected else -1
                if email_field_index >= 0:
                    messages_since_email = message_count - len(state.fields_collected) * 2
                    if messages_since_email >= self.MESSAGE_COUNT_PHONE:
                        # Only ask for phone in specific contexts (demo, callback mentions)
                        return UserInfoField.PHONE
            else:
                print(f"[UserInfoManager] ⏭️ Skipping 'phone' - permanently declined")

        return None

    def _calculate_collection_weight(self, state: UserInfoState) -> float:
        """
        Calculate collection weight (0.0 to 1.0).
        Starts at 0.8 (80% collection focus) and decreases as fields are collected.
        """
        # Base formula: weight = 0.8 * (1 - completion_percentage)
        weight = max(0.0, 0.8 - (0.8 * state.completion_percentage))

        # Minimum weight of 0.2 (20%) for incomplete collections
        if state.completion_percentage < 1.0:
            weight = max(0.2, weight)

        return round(weight, 2)

    def _get_ask_count(self, state: UserInfoState, field: UserInfoField) -> int:
        """Get ask count for a specific field"""
        return getattr(state, f'{field.value}_ask_count', 0)

    def _increment_ask_count(self, state: UserInfoState, field: UserInfoField):
        """Increment ask count for a field"""
        current = getattr(state, f'{field.value}_ask_count', 0)
        setattr(state, f'{field.value}_ask_count', current + 1)

    def _increment_rejection_count(self, state: UserInfoState, field: UserInfoField):
        """
        Increment rejection count when user declines to provide a field.
        After 4 rejections, mark field as permanently declined.
        """
        current = getattr(state, f'{field.value}_rejection_count', 0)
        new_count = current + 1
        setattr(state, f'{field.value}_rejection_count', new_count)

        print(f"[UserInfoManager] Field '{field.value}' rejected {new_count} time(s)")

        # After 4 rejections, permanently decline this field
        if new_count >= 4 and field.value not in state.fields_declined:
            state.fields_declined.append(field.value)
            print(f"[UserInfoManager] ❌ Field '{field.value}' permanently declined after 4 rejections")

    def _is_field_declined(self, state: UserInfoState, field: UserInfoField) -> bool:
        """Check if a field has been permanently declined (4+ rejections)"""
        return field.value in state.fields_declined

    def _get_rejection_count(self, state: UserInfoState, field: UserInfoField) -> int:
        """Get rejection count for a specific field"""
        return getattr(state, f'{field.value}_rejection_count', 0)

    # ========================================================================
    # PROMPT GENERATION
    # ========================================================================

    def _generate_prompt(
        self,
        field: UserInfoField,
        message: str,
        detected_intent: Optional[str] = None,
        ask_count: int = 0
    ) -> str:
        """
        Generate natural prompt to collect user info.
        Context-aware based on message content and intent.
        """
        # Softer approach on second+ ask
        is_retry = ask_count > 0

        if field == UserInfoField.NAME:
            return self._generate_name_prompt(message, detected_intent, is_retry)
        elif field == UserInfoField.EMAIL:
            return self._generate_email_prompt(message, detected_intent, is_retry)
        elif field == UserInfoField.PHONE:
            return self._generate_phone_prompt(message, detected_intent, is_retry)
        elif field == UserInfoField.REQUIREMENTS:
            return self._generate_requirements_prompt(message, detected_intent, is_retry)

        return ""

    def _generate_name_prompt(self, message: str, intent: Optional[str], is_retry: bool) -> str:
        """Generate professional, natural name prompt"""
        if is_retry:
            prompts = [
                "By the way, I'd love to personalize our conversation. What should I call you?",
                "I realize I haven't asked your name yet. May I know who I'm chatting with?",
                "To better assist you, what's your name?"
            ]
        else:
            prompts = [
                "By the way, what's your name? I'd love to make this conversation more personal.",
                "I'd like to personalize our chat. What should I call you?",
                "Before we continue, may I know your name?"
            ]

        # Contextual variations
        if "demo" in message.lower() or intent == "demo_request":
            return "Perfect! I'd be happy to help with a demo. What's your name?"
        elif "pricing" in message.lower() or "price" in message.lower():
            return "I can provide detailed pricing information. To personalize it for you, what's your name?"
        elif "help" in message.lower():
            return "I'm here to help! What's your name so I can assist you better?"

        import random
        return random.choice(prompts)

    def _generate_email_prompt(self, message: str, intent: Optional[str], is_retry: bool) -> str:
        """
        Generate professional email prompt.
        Encourages work email for better experience.
        """
        if is_retry:
            prompts = [
                "I'd love to send you more information. Could you share your work email?",
                "To send you detailed information, what's your professional email address?",
                "For personalized business insights, may I have your work email?"
            ]
        else:
            prompts = [
                "I can send you detailed information and insights. What's your work email address?",
                "To share valuable resources with you, may I have your professional email?",
                "I'd be happy to send you comprehensive details. What's your work email?"
            ]

        # Contextual variations (always encourage work email)
        if "send" in message.lower() or "email" in message.lower():
            return "Of course! What's your work email address, so I can send you professional information?"
        elif "report" in message.lower() or "analysis" in message.lower():
            return "I can send you a detailed business report. What's your work email?"
        elif "demo" in message.lower():
            return "Perfect! What's your work email for the demo invitation and follow-up resources?"
        elif "price" in message.lower() or "pricing" in message.lower():
            return "I can email you detailed pricing information. What's your work email?"

        import random
        return random.choice(prompts)

    def _generate_phone_prompt(self, message: str, intent: Optional[str], is_retry: bool) -> str:
        """Generate professional phone prompt (only in specific contexts)"""
        if is_retry:
            return "If you'd prefer a personalized phone call from our team, what's the best number to reach you?"

        # Only ask for phone in specific contexts
        if "call" in message.lower() or "callback" in message.lower():
            return "I'd be happy to arrange a callback from our team. What's your phone number?"
        elif "demo" in message.lower():
            return "For a personalized phone demo, what's the best number to reach you?"
        elif "urgent" in message.lower() or "speak" in message.lower():
            return "I can have our team call you right away. What's your phone number?"
        elif "talk" in message.lower():
            return "I can connect you with our team via phone. What number should they call?"

        # Generic (low priority - only if explicitly appropriate)
        return "For personalized phone support, what's the best number to reach you?"

    def _generate_requirements_prompt(self, message: str, intent: Optional[str], is_retry: bool) -> str:
        """Generate engaging requirements prompt"""
        if is_retry:
            return "To better assist you, could you tell me what you're mainly looking to accomplish?"

        prompts = [
            "So I can provide the most relevant information, what are your main business goals with our platform?",
            "What's your primary interest - market research, trade analytics, or supplier discovery?",
            "To personalize your experience, what are you looking to achieve?"
        ]

        # Contextual
        if "import" in message.lower() or "export" in message.lower():
            return "It sounds like you're interested in trade data. What specific market or product are you researching?"
        elif "supplier" in message.lower():
            return "Great! Are you looking for suppliers in a specific country or product category?"

        import random
        return random.choice(prompts)

    # ========================================================================
    # EXTRACTION
    # ========================================================================

    async def extract_from_message(
        self,
        session_id: str,
        message: str,
        field: Optional[UserInfoField] = None
    ) -> Optional[ExtractionResult]:
        """
        Extract user info from message.

        Args:
            session_id: Session identifier
            message: User's message
            field: Expected field (if we just asked for it)

        Returns:
            ExtractionResult or None if nothing extracted
        """
        state = await self.get_state(session_id)

        # If we have a hint about what field we asked for, try that first
        if field:
            result = self._extract_field(message, field)
            if result and result.extracted:
                # Save extracted value
                await self._save_extracted_field(state, field, result.value)
                return result

        # Try to extract any field opportunistically
        for check_field in [UserInfoField.NAME, UserInfoField.EMAIL, UserInfoField.PHONE]:
            if getattr(state, check_field.value):
                continue  # Already have this field

            result = self._extract_field(message, check_field)
            if result and result.extracted:
                await self._save_extracted_field(state, check_field, result.value)
                return result

        return None

    def _extract_field(self, message: str, field: UserInfoField) -> ExtractionResult:
        """Extract specific field from message using regex patterns"""
        if field == UserInfoField.NAME:
            return self._extract_name(message)
        elif field == UserInfoField.EMAIL:
            return self._extract_email(message)
        elif field == UserInfoField.PHONE:
            return self._extract_phone(message)
        elif field == UserInfoField.REQUIREMENTS:
            return self._extract_requirements(message)

        return ExtractionResult(field=field, extracted=False)

    def _extract_name(self, message: str) -> ExtractionResult:
        """Extract name from message"""
        message_lower = message.lower().strip()

        # Block common greetings and short words that aren't names
        common_greetings = ['hi', 'hello', 'hey', 'yo', 'sup', 'ok', 'yes', 'no', 'sure', 'thanks', 'bye']
        if message_lower in common_greetings:
            return ExtractionResult(field=UserInfoField.NAME, extracted=False)

        # Pattern 1: "my name is X" or "I'm X" or "I am X"
        patterns = [
            r"(?:my name is|i'm|i am|call me|this is)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*$"  # Just a name (capitalized)
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Validate: at least 2 chars, no numbers, not a greeting
                if (len(name) >= 2 and
                    not any(char.isdigit() for char in name) and
                    name.lower() not in common_greetings):
                    return ExtractionResult(
                        field=UserInfoField.NAME,
                        value=name.title(),
                        confidence=0.9,
                        extracted=True,
                        method="regex"
                    )

        return ExtractionResult(field=UserInfoField.NAME, extracted=False)

    def _extract_email(self, message: str) -> ExtractionResult:
        """
        Extract and validate email from message.
        Blocks disposable emails and encourages work emails.
        """
        # Email regex pattern
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(pattern, message)

        if match:
            email = match.group(0).lower()

            # Validate email (check disposable, work email, etc.)
            is_valid, email_type, validation_message = self.email_validator.validate_email(email)

            if not is_valid:
                # Disposable or invalid email detected
                print(f"[UserInfoManager] Invalid email rejected: {email} (type: {email_type})")
                return ExtractionResult(
                    field=UserInfoField.EMAIL,
                    value=None,
                    confidence=0.0,
                    extracted=False,
                    method="validation_failed"
                )

            # Valid email - check type
            confidence = 0.95 if email_type == "work" else 0.85
            print(f"[UserInfoManager] Valid email accepted: {email} (type: {email_type})")

            return ExtractionResult(
                field=UserInfoField.EMAIL,
                value=email,
                confidence=confidence,
                extracted=True,
                method="regex+validation"
            )

        return ExtractionResult(field=UserInfoField.EMAIL, extracted=False)

    def _extract_phone(self, message: str) -> ExtractionResult:
        """Extract phone number from message"""
        # Phone patterns (various formats)
        patterns = [
            r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # International
            r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',  # US format
            r'\d{10}',  # Simple 10 digits
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                phone = match.group(0)
                # Clean up
                phone = re.sub(r'[^\d+]', '', phone)
                if len(phone) >= 10:
                    return ExtractionResult(
                        field=UserInfoField.PHONE,
                        value=phone,
                        confidence=0.85,
                        extracted=True,
                        method="regex"
                    )

        return ExtractionResult(field=UserInfoField.PHONE, extracted=False)

    def _extract_requirements(self, message: str) -> ExtractionResult:
        """Extract requirements from message (simple keyword-based)"""
        message_lower = message.lower()

        requirements = {}

        # Use case detection
        if any(word in message_lower for word in ['import', 'export', 'trade', 'shipment']):
            requirements['use_case'] = 'trade_intelligence'
        elif any(word in message_lower for word in ['market', 'research', 'analysis']):
            requirements['use_case'] = 'market_research'
        elif any(word in message_lower for word in ['supplier', 'buyer', 'partner']):
            requirements['use_case'] = 'supplier_discovery'

        # Industry detection
        industries = ['manufacturing', 'retail', 'logistics', 'agriculture', 'technology']
        for industry in industries:
            if industry in message_lower:
                requirements['industry'] = industry
                break

        if requirements:
            return ExtractionResult(
                field=UserInfoField.REQUIREMENTS,
                value=json.dumps(requirements),
                confidence=0.7,
                extracted=True,
                method="keyword"
            )

        return ExtractionResult(field=UserInfoField.REQUIREMENTS, extracted=False)

    async def _save_extracted_field(
        self,
        state: UserInfoState,
        field: UserInfoField,
        value: str
    ):
        """Save extracted field to state and database"""
        # Update state
        setattr(state, field.value, value)

        # Add to fields_collected if not already there
        if field.value not in state.fields_collected:
            state.fields_collected.append(field.value)

            # Set first_field_at if this is the first field
            if not state.first_field_at:
                state.first_field_at = datetime.now()

        # Update completion percentage
        state.completion_percentage = sum(
            self.FIELD_WEIGHTS[UserInfoField(f)]
            for f in state.fields_collected
        )

        # Mark completed if all priority fields collected (name + email)
        if state.name and state.email:
            if state.completion_percentage >= 0.6 and not state.completed_at:
                state.completed_at = datetime.now()

        # Update timestamps
        state.updated_at = datetime.now()

        # Save to Redis and MySQL
        self._save_state_to_redis(state)
        await self._save_state_to_mysql(state, field.value, value)

        print(f"[UserInfoManager] Saved {field.value}={value} for {state.session_id}")
        print(f"                  Completion: {state.completion_percentage * 100:.1f}%")

    # ========================================================================
    # RESISTANCE DETECTION
    # ========================================================================

    async def detect_resistance(
        self,
        session_id: str,
        message: str
    ) -> bool:
        """
        Detect if user is resisting information collection.

        Resistance signals:
        - Explicit refusal: "no", "skip", "prefer not to say"
        - Topic change without providing info
        - Short dismissive responses
        """
        message_lower = message.lower().strip()

        # Explicit refusal patterns
        refusal_patterns = [
            r'\b(no|nope|nah)\b',
            r'\bskip\b',
            r'\bprefer not to\b',
            r'\bnone of your business\b',
            r'\bdon\'t want to\b',
            r'\blater\b',
            r'\bmaybe later\b',
        ]

        for pattern in refusal_patterns:
            if re.search(pattern, message_lower):
                # Track rejection for the field we just asked about
                state = await self.get_state(session_id)
                if state.last_field_asked:
                    try:
                        field = UserInfoField(state.last_field_asked)
                        self._increment_rejection_count(state, field)
                        # Save rejection count to database
                        await self._save_rejection_to_mysql(state, field)
                    except ValueError:
                        pass  # Invalid field name

                await self._pause_collection(session_id)
                return True

        # Short dismissive responses (< 10 chars, no info)
        if len(message) < 10 and not any(char.isdigit() or '@' in message for char in message):
            state = await self.get_state(session_id)
            # If they've ignored us twice, pause AND track as rejection
            if state.last_field_asked:
                ask_count = self._get_ask_count(state, UserInfoField(state.last_field_asked))
                if ask_count >= 2:
                    # Track as rejection (ignored multiple times)
                    try:
                        field = UserInfoField(state.last_field_asked)
                        self._increment_rejection_count(state, field)
                        # Save rejection count to database
                        await self._save_rejection_to_mysql(state, field)
                    except ValueError:
                        pass

                    await self._pause_collection(session_id)
                    return True

        return False

    async def check_disposable_email(self, session_id: str, message: str) -> Optional[str]:
        """
        Check if message contains disposable email and return helpful message.

        Returns:
            Natural message to user if disposable email detected, None otherwise
        """
        # Extract potential email
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(pattern, message)

        if match:
            email = match.group(0).lower()

            # Validate
            is_valid, email_type, validation_message = self.email_validator.validate_email(email)

            if not is_valid and email_type == "disposable":
                # Track attempt
                if session_id not in self._email_validation_attempts:
                    self._email_validation_attempts[session_id] = 0
                self._email_validation_attempts[session_id] += 1

                attempts = self._email_validation_attempts[session_id]

                # Provide progressively helpful messages (professional tone)
                if attempts == 1:
                    return validation_message
                elif attempts == 2:
                    return (
                        "I'd love to send you detailed trade insights and market reports. "
                        "What's your preferred work email address?"
                    )
                else:
                    return (
                        "No problem! Feel free to continue exploring. "
                        "If you'd like detailed reports or personalized assistance later, just let me know."
                    )

        return None

    async def _pause_collection(self, session_id: str):
        """Pause collection for this session"""
        state = await self.get_state(session_id)
        state.collection_paused = True
        state.pause_until_message_count = state.current_message_count + self.PAUSE_MESSAGES

        self._save_state_to_redis(state)
        await self.db_service.update_collection_pause(
            session_id,
            paused=True,
            pause_until_message_count=state.pause_until_message_count
        )

        print(f"[UserInfoManager] Collection paused for {session_id} (resume at message {state.pause_until_message_count})")

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def get_user_info(self, session_id: str) -> Dict[str, Any]:
        """Get user info for a session"""
        state = await self.get_state(session_id)
        return {
            "session_id": state.session_id,
            "name": state.name,
            "email": state.email,
            "phone": state.phone,
            "requirements": state.requirements,
            "completion_percentage": state.completion_percentage,
            "fields_collected": state.fields_collected,
            "collection_paused": state.collection_paused,
            "current_phase": state.current_phase.value if isinstance(state.current_phase, CollectionPhase) else state.current_phase
        }

    async def pause_collection_manually(self, session_id: str, pause_for_messages: int = 5):
        """Manually pause collection for a session"""
        state = await self.get_state(session_id)
        state.collection_paused = True
        state.pause_until_message_count = state.current_message_count + pause_for_messages

        self._save_state_to_redis(state)
        await self.db_service.update_collection_pause(
            session_id,
            paused=True,
            pause_until_message_count=state.pause_until_message_count
        )

        return {
            "success": True,
            "paused_until_message_count": state.pause_until_message_count
        }
