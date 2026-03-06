"""
Credit Manager - Virtual Credit System for Chatbot

Manages user credits (hidden from user) that trigger lead conversion when exhausted.
Credits are deducted based on query intent - data queries cost more than general queries.
"""

import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

# Import Redis manager type for type hints
try:
    from redis_memory import RedisMemoryManager
except ImportError:
    RedisMemoryManager = None


@dataclass
class CreditConfig:
    """Configuration for credit system"""
    INITIAL_CREDITS: int = 50  # Starting credits for new sessions (increased for better UX)

    # Credit costs by intent type - LOW for general, HIGH for data queries
    CREDIT_COSTS: Dict[str, int] = None

    # Multiplier applied after "Continue Chat" is pressed
    CONTINUE_CHAT_MULTIPLIER: float = 1.5  # Reduced from 2.0 for better UX

    # Bonus credits given when user clicks "Continue Chatting"
    CONTINUE_BONUS_CREDITS: int = 8

    def __post_init__(self):
        if self.CREDIT_COSTS is None:
            self.CREDIT_COSTS = {
                # Data-specific queries (HIGH COST)
                "search_trade_data": 3,    # Most detailed - importer/exporter/trade records
                "country_to_country": 2,   # Bilateral trade between countries
                "hs_code": 2,              # HS code/chapter queries
                "search_country_data": 2,  # Country overview data

                # General queries (LOW COST)
                "general": 1,              # KB-only, platform questions
                "unknown": 1,              # Unknown intent, treat as general

                # Free queries (NO COST)
                "greeting": 0,             # Free - hello, hi, thanks
                "out_of_scope": 0          # Free - non-trade questions
            }


# Global config instance
CREDIT_CONFIG = CreditConfig()


class CreditManager:
    """
    Manages virtual credits for chatbot sessions.

    Credits are hidden from the user but track usage.
    When exhausted, triggers lead conversion UI.

    Redis Keys:
    - session:{session_id}:credits - Credit state JSON
    """

    REDIS_KEY_PREFIX = "session"
    CREDITS_KEY_SUFFIX = "credits"
    TTL_SECONDS = 7 * 24 * 3600  # 7 days

    def __init__(self, redis_manager: Optional[RedisMemoryManager] = None):
        """
        Initialize CreditManager with Redis backend.

        Args:
            redis_manager: RedisMemoryManager instance for persistence
        """
        self.redis = redis_manager
        self.config = CREDIT_CONFIG

        # In-memory fallback if Redis is unavailable
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    def _get_redis_key(self, session_id: str) -> str:
        """Generate Redis key for credit storage"""
        return f"{self.REDIS_KEY_PREFIX}:{session_id}:{self.CREDITS_KEY_SUFFIX}"

    def _get_default_state(self) -> Dict[str, Any]:
        """Get default credit state for new sessions"""
        return {
            "remaining": self.config.INITIAL_CREDITS,
            "initial": self.config.INITIAL_CREDITS,
            "used": 0,
            "continue_chat_used": False,
            "multiplier": 1.0,
            "exhausted_at": None,
            "last_deduction": None,
            "created_at": datetime.now().isoformat()
        }

    def get_credits(self, session_id: str) -> Dict[str, Any]:
        """
        Get current credit state for a session.
        Creates new credit allocation if session doesn't exist.

        Args:
            session_id: Unique session identifier

        Returns:
            Dict containing credit state
        """
        key = self._get_redis_key(session_id)

        # Try Redis first
        if self.redis:
            try:
                data = self.redis.client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                print(f"[CREDITS] Redis read error: {e}")

        # Fallback to memory
        if session_id in self._memory_store:
            return self._memory_store[session_id].copy()

        # Initialize new session
        state = self._get_default_state()
        self._save_state(session_id, state)

        return state

    def _save_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """
        Save credit state to storage.

        Args:
            session_id: Session identifier
            state: Credit state to save

        Returns:
            True if saved successfully
        """
        key = self._get_redis_key(session_id)

        # Try Redis first
        if self.redis:
            try:
                self.redis.client.setex(
                    key,
                    self.TTL_SECONDS,
                    json.dumps(state)
                )
                return True
            except Exception as e:
                print(f"[CREDITS] Redis write error: {e}")

        # Fallback to memory
        self._memory_store[session_id] = state.copy()
        return True

    def deduct_credits(
        self,
        session_id: str,
        intent: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Deduct credits based on query intent.

        Args:
            session_id: Session identifier
            intent: Detected intent (e.g., "search_trade_data", "greeting")

        Returns:
            Tuple of (can_proceed, updated_state)
            - can_proceed: False if credits exhausted
            - updated_state: Current credit state
        """
        state = self.get_credits(session_id)

        # Check if already exhausted
        if state.get("exhausted_at") and not state.get("continue_chat_used"):
            return False, state

        # Get base cost for intent
        base_cost = self.config.CREDIT_COSTS.get(intent, 1)

        # Apply multiplier if continue chat was used
        multiplier = state.get("multiplier", 1.0)
        actual_cost = int(base_cost * multiplier)

        # Free intents always proceed
        if actual_cost == 0:
            return True, state

        # Check if enough credits
        remaining = state.get("remaining", 0)

        if remaining < actual_cost:
            # Credits exhausted
            state["exhausted_at"] = datetime.now().isoformat()
            state["remaining"] = 0
            self._save_state(session_id, state)

            print(f"[CREDITS] Session {session_id} exhausted. Intent: {intent}")
            return False, state

        # Deduct credits
        state["remaining"] = remaining - actual_cost
        state["used"] = state.get("used", 0) + actual_cost
        state["last_deduction"] = datetime.now().isoformat()

        self._save_state(session_id, state)

        print(f"[CREDITS] Session {session_id}: -{actual_cost} credits "
              f"({intent}). Remaining: {state['remaining']}")

        return True, state

    def activate_continue_chat(self, session_id: str) -> Dict[str, Any]:
        """
        Activate continue chat mode with slightly higher credit cost.

        Gives user additional credits to continue exploring.

        Args:
            session_id: Session identifier

        Returns:
            Updated credit state
        """
        state = self.get_credits(session_id)

        if state.get("continue_chat_used"):
            # Already used continue chat
            return state

        # Grant bonus credits from config
        bonus_credits = self.config.CONTINUE_BONUS_CREDITS

        state["continue_chat_used"] = True
        state["multiplier"] = self.config.CONTINUE_CHAT_MULTIPLIER
        state["remaining"] = bonus_credits
        state["exhausted_at"] = None  # Reset exhaustion

        self._save_state(session_id, state)

        print(f"[CREDITS] Session {session_id} activated continue chat. "
              f"Bonus: {bonus_credits} credits at {state['multiplier']}x cost")

        return state

    def get_exhaustion_response(self) -> Dict[str, Any]:
        """
        Get the response to show when credits are exhausted.

        Returns:
            Dict with message, actions, and UI configuration
        """
        return {
            "message": "I've shared some valuable insights with you! To continue exploring our comprehensive trade data and get personalized recommendations...",
            "actions": [
                {
                    "type": "schedule_demo",
                    "label": "Schedule a Demo",
                    "description": "See how we can help your business"
                },
                {
                    "type": "whatsapp",
                    "label": "WhatsApp Chat",
                    "description": "Chat with our team instantly"
                },
                {
                    "type": "chat_with_us",
                    "label": "Talk to Live Agent",
                    "description": "Talk to our support team"
                },
                {
                    "type": "continue_chat",
                    "label": "Continue Chatting",
                    "description": "Keep exploring (limited)"
                }
            ],
            "show_continue_chat": True
        }

    def reset_credits(self, session_id: str) -> Dict[str, Any]:
        """
        Reset credits for a session (e.g., on session reset).

        Args:
            session_id: Session identifier

        Returns:
            New credit state
        """
        state = self._get_default_state()
        self._save_state(session_id, state)

        print(f"[CREDITS] Session {session_id} credits reset")
        return state

    def get_cost_for_intent(self, intent: str, session_id: Optional[str] = None) -> int:
        """
        Get the credit cost for a given intent.

        Args:
            intent: Query intent
            session_id: Optional session ID to check multiplier

        Returns:
            Credit cost (with multiplier applied if applicable)
        """
        base_cost = self.config.CREDIT_COSTS.get(intent, 1)

        if session_id:
            state = self.get_credits(session_id)
            multiplier = state.get("multiplier", 1.0)
            return int(base_cost * multiplier)

        return base_cost


# Singleton instance (initialized with Redis in fastapi_chatbot.py)
_credit_manager: Optional[CreditManager] = None


def get_credit_manager(redis_manager: Optional[RedisMemoryManager] = None) -> CreditManager:
    """
    Get or create CreditManager singleton.

    Args:
        redis_manager: Optional Redis manager to initialize with

    Returns:
        CreditManager instance
    """
    global _credit_manager

    if _credit_manager is None:
        _credit_manager = CreditManager(redis_manager)
    elif redis_manager and _credit_manager.redis is None:
        _credit_manager.redis = redis_manager

    return _credit_manager


def init_credit_manager(redis_manager: RedisMemoryManager) -> CreditManager:
    """
    Initialize CreditManager with Redis backend.

    Args:
        redis_manager: Redis manager instance

    Returns:
        Initialized CreditManager
    """
    global _credit_manager
    _credit_manager = CreditManager(redis_manager)
    print("[CREDITS] CreditManager initialized with Redis backend")
    return _credit_manager
