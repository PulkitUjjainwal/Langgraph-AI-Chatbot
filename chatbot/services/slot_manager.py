"""
Slot Manager - Conversational Parameter Collection for Chatbot

Manages the collection of required parameters (slots) for different query intents.
Tracks what information has been collected and generates clarifying questions
when required parameters are missing.
"""

import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# Import Redis manager type for type hints
try:
    from redis_memory import RedisMemoryManager
except ImportError:
    RedisMemoryManager = None


@dataclass
class SlotDefinition:
    """Definition of a slot (parameter) that can be collected"""
    name: str
    display_name: str
    question: str
    suggestions: Optional[List[str]] = None
    required: bool = True
    validator: Optional[str] = None  # Optional validation function name


@dataclass
class SlotState:
    """Current state of collected slots for a session"""
    intent: Optional[str] = None
    slots: Dict[str, Any] = field(default_factory=dict)
    missing_slots: List[str] = field(default_factory=list)
    last_asked_slot: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SlotConfig:
    """Configuration for slot requirements by intent"""

    # Required slots for each intent type
    # NOTE: direction is NOT required - we default to "import" as most common use case
    REQUIRED_SLOTS: Dict[str, List[str]] = {
        "search_country_data": ["country"],  # direction defaults to import
        "search_trade_data": ["country"],    # + product OR hs_code, direction defaults to import
        "country_to_country": ["origin_country", "destination_country"],  # direction defaults to export
        "hs_code": ["country", "hs_code"],   # direction defaults to import
    }

    # Optional slots (at least one required for some intents)
    OPTIONAL_SLOTS: Dict[str, List[str]] = {
        "search_trade_data": ["product", "hs_code"],  # At least one required
    }

    # Default values for slots when not provided
    DEFAULT_SLOT_VALUES: Dict[str, Dict[str, str]] = {
        "search_country_data": {"direction": "import"},
        "search_trade_data": {"direction": "import"},
        "country_to_country": {"direction": "export"},
        "hs_code": {"direction": "import"},
    }

    # Slot definitions with questions and suggestions
    SLOT_DEFINITIONS: Dict[str, SlotDefinition] = {
        "country": SlotDefinition(
            name="country",
            display_name="Country",
            question="Which country are you interested in?",
            suggestions=["India", "USA", "China", "Germany", "Indonesia"],
        ),
        "direction": SlotDefinition(
            name="direction",
            display_name="Trade Direction",
            question="Are you interested in imports or exports?",
            suggestions=["Imports", "Exports"],
        ),
        "product": SlotDefinition(
            name="product",
            display_name="Product",
            question="What product or HS code are you interested in?",
            suggestions=None,  # Free text
        ),
        "hs_code": SlotDefinition(
            name="hs_code",
            display_name="HS Code",
            question="What HS code or chapter are you looking for?",
            suggestions=None,  # Free text
        ),
        "origin_country": SlotDefinition(
            name="origin_country",
            display_name="Origin Country",
            question="Which country is the origin (exporting country)?",
            suggestions=["India", "USA", "China", "Germany"],
        ),
        "destination_country": SlotDefinition(
            name="destination_country",
            display_name="Destination Country",
            question="Which country is the destination (importing country)?",
            suggestions=["India", "USA", "China", "Germany"],
        ),
    }


class SlotManager:
    """
    Manages slot collection for conversational parameter gathering.

    Tracks what parameters have been collected for a query and generates
    appropriate clarifying questions when required parameters are missing.

    Redis Keys:
    - session:{session_id}:slots - Slot state JSON
    """

    REDIS_KEY_PREFIX = "session"
    SLOTS_KEY_SUFFIX = "slots"
    TTL_SECONDS = 7 * 24 * 3600  # 7 days

    def __init__(self, redis_manager: Optional[RedisMemoryManager] = None):
        """
        Initialize SlotManager with Redis backend.

        Args:
            redis_manager: RedisMemoryManager instance for persistence
        """
        self.redis = redis_manager
        self.config = SlotConfig()

        # In-memory fallback if Redis is unavailable
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    def _get_redis_key(self, session_id: str) -> str:
        """Generate Redis key for slot storage"""
        return f"{self.REDIS_KEY_PREFIX}:{session_id}:{self.SLOTS_KEY_SUFFIX}"

    def _state_to_dict(self, state: SlotState) -> Dict[str, Any]:
        """Convert SlotState to dict for storage"""
        return {
            "intent": state.intent,
            "slots": state.slots,
            "missing_slots": state.missing_slots,
            "last_asked_slot": state.last_asked_slot,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }

    def _dict_to_state(self, data: Dict[str, Any]) -> SlotState:
        """Convert dict to SlotState"""
        return SlotState(
            intent=data.get("intent"),
            slots=data.get("slots", {}),
            missing_slots=data.get("missing_slots", []),
            last_asked_slot=data.get("last_asked_slot"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def get_slots(self, session_id: str) -> SlotState:
        """
        Get current slot state for a session.

        Args:
            session_id: Session identifier

        Returns:
            SlotState object
        """
        key = self._get_redis_key(session_id)

        # Try Redis first
        if self.redis:
            try:
                data = self.redis.client.get(key)
                if data:
                    return self._dict_to_state(json.loads(data))
            except Exception as e:
                print(f"[SLOTS] Redis read error: {e}")

        # Fallback to memory
        if session_id in self._memory_store:
            return self._dict_to_state(self._memory_store[session_id])

        # Return empty state
        return SlotState()

    def _save_state(self, session_id: str, state: SlotState) -> bool:
        """
        Save slot state to storage.

        Args:
            session_id: Session identifier
            state: SlotState to save

        Returns:
            True if saved successfully
        """
        key = self._get_redis_key(session_id)
        state.updated_at = datetime.now().isoformat()
        data = self._state_to_dict(state)

        # Try Redis first
        if self.redis:
            try:
                self.redis.client.setex(
                    key,
                    self.TTL_SECONDS,
                    json.dumps(data)
                )
                return True
            except Exception as e:
                print(f"[SLOTS] Redis write error: {e}")

        # Fallback to memory
        self._memory_store[session_id] = data
        return True

    def update_slots(
        self,
        session_id: str,
        intent: str,
        extracted_params: Dict[str, Any]
    ) -> SlotState:
        """
        Update slots with newly extracted parameters.

        Args:
            session_id: Session identifier
            intent: Detected intent
            extracted_params: Parameters extracted from query

        Returns:
            Updated SlotState
        """
        state = self.get_slots(session_id)

        # Check if intent changed (topic change)
        if state.intent and state.intent != intent:
            # Clear slots on topic change
            print(f"[SLOTS] Intent changed from {state.intent} to {intent}, clearing slots")
            state = SlotState()

        # Check if key params changed (new query about different entity)
        # This prevents old "china" from being used when user asks about "afghanistan"
        key_params = ["country", "hs_code", "origin_country", "destination_country", "product"]
        for key in key_params:
            new_value = extracted_params.get(key)
            old_value = state.slots.get(key)
            if new_value and old_value and new_value.lower().strip() != old_value.lower().strip():
                print(f"[SLOTS] Key param '{key}' changed from '{old_value}' to '{new_value}', clearing all slots")
                state = SlotState()
                break

        state.intent = intent

        # Normalize and update slots
        for key, value in extracted_params.items():
            if value:  # Only update non-empty values
                # Normalize direction values
                if key == "direction":
                    value = self._normalize_direction(value)
                # Normalize country names
                if key in ["country", "origin_country", "destination_country"]:
                    value = self._normalize_country(value)

                state.slots[key] = value

                # Clear last_asked_slot if we just filled it
                if key == state.last_asked_slot:
                    print(f"[SLOTS] Filled pending slot '{key}' with '{value}'")
                    state.last_asked_slot = None

        # Calculate missing slots
        state.missing_slots = self._get_missing_slots(intent, state.slots)

        self._save_state(session_id, state)

        print(f"[SLOTS] Session {session_id}: intent={intent}, "
              f"slots={state.slots}, missing={state.missing_slots}")

        return state

    def _normalize_direction(self, value: str) -> str:
        """Normalize direction value to 'import' or 'export'"""
        value = value.lower().strip()
        if value in ["import", "imports", "importing", "importer", "importers"]:
            return "import"
        if value in ["export", "exports", "exporting", "exporter", "exporters"]:
            return "export"
        return value

    def _normalize_country(self, value: str) -> str:
        """Normalize country name to lowercase, URL-safe format with hyphens"""
        # Use hyphens instead of %20 for URL paths (API client expects this format)
        return value.lower().strip().replace(" ", "-")

    def _get_missing_slots(self, intent: str, slots: Dict[str, Any]) -> List[str]:
        """
        Get list of missing required slots for an intent.

        Args:
            intent: Query intent
            slots: Currently collected slots

        Returns:
            List of missing slot names
        """
        required = self.config.REQUIRED_SLOTS.get(intent, [])
        optional = self.config.OPTIONAL_SLOTS.get(intent, [])

        missing = []

        # Check required slots
        for slot in required:
            if slot not in slots or not slots[slot]:
                missing.append(slot)

        # For search_trade_data, need at least one of product OR hs_code
        if intent == "search_trade_data" and optional:
            has_optional = any(slot in slots and slots[slot] for slot in optional)
            if not has_optional:
                # Add product as the preferred optional to ask for
                missing.append("product")

        return missing

    def get_missing_slot_question(
        self,
        session_id: str,
        intent: str,
        slots: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Get the next clarifying question to ask for missing slots.

        Args:
            session_id: Session identifier
            intent: Query intent
            slots: Currently collected slots

        Returns:
            Dict with question info, or None if no slots missing
        """
        missing = self._get_missing_slots(intent, slots)

        if not missing:
            return None

        # Get the first missing slot
        slot_name = missing[0]
        definition = self.config.SLOT_DEFINITIONS.get(slot_name)

        if not definition:
            return None

        # Track which slot we're asking about
        state = self.get_slots(session_id)
        state.last_asked_slot = slot_name
        self._save_state(session_id, state)

        return {
            "slot_name": slot_name,
            "question": definition.question,
            "suggestions": definition.suggestions,
            "display_name": definition.display_name,
        }

    def has_all_required_slots(self, intent: str, slots: Dict[str, Any]) -> bool:
        """
        Check if all required slots are filled for an intent.

        Args:
            intent: Query intent
            slots: Collected slots

        Returns:
            True if all required slots are filled
        """
        missing = self._get_missing_slots(intent, slots)
        return len(missing) == 0

    def get_slots_with_defaults(self, intent: str, slots: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get slots with default values applied.

        Args:
            intent: Query intent
            slots: Collected slots

        Returns:
            Slots dict with defaults applied
        """
        result = slots.copy()
        defaults = self.config.DEFAULT_SLOT_VALUES.get(intent, {})

        for key, default_value in defaults.items():
            if key not in result or not result[key]:
                result[key] = default_value

        return result

    def clear_slots(self, session_id: str) -> bool:
        """
        Clear all slots for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared successfully
        """
        key = self._get_redis_key(session_id)

        if self.redis:
            try:
                self.redis.client.delete(key)
            except Exception as e:
                print(f"[SLOTS] Redis delete error: {e}")

        if session_id in self._memory_store:
            del self._memory_store[session_id]

        print(f"[SLOTS] Cleared slots for session: {session_id}")
        return True

    def generate_url(self, intent: str, slots: Dict[str, Any]) -> Optional[str]:
        """
        Generate the explore URL based on intent and collected slots.

        Args:
            intent: Query intent
            slots: Collected slots

        Returns:
            URL string or None if slots incomplete
        """
        if not self.has_all_required_slots(intent, slots):
            return None

        # Apply default values
        slots = self.get_slots_with_defaults(intent, slots)

        base_url = "https://www.marketinsidedata.com/en"

        if intent == "search_country_data":
            country = slots.get("country", "")
            direction = slots.get("direction", "import")
            direction_suffix = "imports" if direction == "import" else "exports"
            return f"{base_url}/country/{country}/{direction_suffix}"

        elif intent == "search_trade_data":
            country = slots.get("country", "")
            direction = slots.get("direction", "import")
            product = slots.get("product", "")
            hs_code = slots.get("hs_code", "")
            entity_type = slots.get("entity_type", "trade")

            # Determine endpoint based on entity_type
            # importer/exporter/supplier/buyer/trade
            endpoint = entity_type if entity_type in ["importer", "exporter", "suppliers", "buyers", "trade"] else "trade"
            params = f"type={direction}&country={country}"

            if product:
                params += f"&product={product.lower().replace(' ', '%20')}"
            elif hs_code:
                params += f"&hs_code={hs_code}"

            return f"{base_url}/search-data/{endpoint}?{params}"

        elif intent == "country_to_country":
            origin = slots.get("origin_country", "").title().replace("%20", " ").replace(" ", "%20")
            destination = slots.get("destination_country", "").title().replace("%20", " ").replace(" ", "%20")
            direction = slots.get("direction", "export")
            return f"{base_url}/cntry/{origin}-{direction}-{destination}"

        elif intent == "hs_code":
            country = slots.get("country", "")
            direction = slots.get("direction", "import")
            hs_code = slots.get("hs_code", "")
            return f"{base_url}/chapter/{country}-{direction}-hs-code-{hs_code}"

        return None


# Singleton instance (initialized with Redis in fastapi_chatbot.py)
_slot_manager: Optional[SlotManager] = None


def get_slot_manager(redis_manager: Optional[RedisMemoryManager] = None) -> SlotManager:
    """
    Get or create SlotManager singleton.

    Args:
        redis_manager: Optional Redis manager to initialize with

    Returns:
        SlotManager instance
    """
    global _slot_manager

    if _slot_manager is None:
        _slot_manager = SlotManager(redis_manager)
    elif redis_manager and _slot_manager.redis is None:
        _slot_manager.redis = redis_manager

    return _slot_manager


def init_slot_manager(redis_manager: RedisMemoryManager) -> SlotManager:
    """
    Initialize SlotManager with Redis backend.

    Args:
        redis_manager: Redis manager instance

    Returns:
        Initialized SlotManager
    """
    global _slot_manager
    _slot_manager = SlotManager(redis_manager)
    print("[SLOTS] SlotManager initialized with Redis backend")
    return _slot_manager
