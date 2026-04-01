"""
Slot Manager - Conversational Parameter Collection for Chatbot

Manages the collection of required parameters (slots) for different query intents.
Tracks what information has been collected and generates clarifying questions
when required parameters are missing.
"""

import json
import re
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
    slot_ask_counts: Dict[str, int] = field(default_factory=dict)  # Track how many times each slot was asked
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SlotConfig:
    """Configuration for slot requirements by intent"""

    # List of continents (not countries) - these should use KB data, not API
    CONTINENTS = {
        "africa", "asia", "europe", "north america", "south america",
        "oceania", "oceania australia", "antarctica", "america",
        "asia pacific", "global"
    }

    # Restricted countries - don't show data, redirect to support/demo
    # These countries require users to schedule a demo or contact support
    RESTRICTED_COUNTRIES = {
        "india"
    }

    # Complex query patterns - queries needing multiple API calls
    # These should redirect to support/dashboard instead of partial answers
    # NOTE: Only detect queries that ACTUALLY need 2+ specific country API calls
    COMPLEX_QUERY_PATTERNS = {
        # Comparison keywords (need 2+ specific countries to be complex)
        "comparison_keywords": [
            " vs ", " vs. ", " versus ", " compared to ", " compare ",
            " comparison between ", " difference between ", " differences between "
        ],
        # Exclusion patterns (e.g., "from usa but not from china")
        "exclusion_patterns": [
            " but not from ", " but not in ", " excluding ", " except from "
        ]
    }

    # Known countries list - Comprehensive list of all countries
    # Including common name variations and abbreviations
    KNOWN_COUNTRIES = {
        # A
        "afghanistan", "albania", "algeria", "andorra", "angola",
        "antigua and barbuda", "antigua", "barbuda", "argentina", "armenia",
        "australia", "austria", "azerbaijan",

        # B
        "bahamas", "the bahamas", "bahrain", "bangladesh", "barbados",
        "belarus", "belgium", "belize", "benin", "bhutan", "bolivia",
        "bosnia and herzegovina", "bosnia", "herzegovina", "botswana", "brazil",
        "brunei", "bulgaria", "burkina faso", "burundi",

        # C
        "cabo verde", "cape verde", "cambodia", "cameroon", "canada",
        "central african republic", "chad", "chile", "china", "colombia",
        "comoros", "congo", "democratic republic of congo", "drc", "costa rica",
        "croatia", "cuba", "cyprus", "czech republic", "czechia",

        # D
        "denmark", "djibouti", "dominica", "dominican republic",

        # E
        "ecuador", "egypt", "el salvador", "equatorial guinea", "eritrea",
        "estonia", "eswatini", "swaziland", "ethiopia",

        # F
        "fiji", "finland", "france",

        # G
        "gabon", "gambia", "the gambia", "georgia", "germany", "ghana",
        "greece", "grenada", "guatemala", "guinea", "guinea-bissau", "guyana",

        # H
        "haiti", "honduras", "hungary",

        # I
        "iceland", "india", "indonesia", "iran", "iraq", "ireland",
        "israel", "italy", "ivory coast", "cote d'ivoire",

        # J
        "jamaica", "japan", "jordan",

        # K
        "kazakhstan", "kenya", "kiribati", "north korea", "south korea",
        "korea", "kosovo", "kuwait", "kyrgyzstan",

        # L
        "laos", "latvia", "lebanon", "lesotho", "liberia", "libya",
        "liechtenstein", "lithuania", "luxembourg",

        # M
        "madagascar", "malawi", "malaysia", "maldives", "mali", "malta",
        "marshall islands", "mauritania", "mauritius", "mexico",
        "micronesia", "moldova", "monaco", "mongolia", "montenegro",
        "morocco", "mozambique", "myanmar", "burma",

        # N
        "namibia", "nauru", "nepal", "netherlands", "new zealand", "nicaragua",
        "niger", "nigeria", "north macedonia", "macedonia", "norway",

        # O
        "oman",

        # P
        "pakistan", "palau", "palestine", "panama", "papua new guinea",
        "paraguay", "peru", "philippines", "poland", "portugal",

        # Q
        "qatar",

        # R
        "romania", "russia", "russian federation", "rwanda",

        # S
        "saint kitts and nevis", "saint lucia", "saint vincent and the grenadines",
        "samoa", "san marino", "sao tome and principe", "saudi arabia",
        "senegal", "serbia", "seychelles", "sierra leone", "singapore",
        "slovakia", "slovenia", "solomon islands", "somalia", "south africa",
        "south sudan", "spain", "sri lanka", "sudan", "suriname", "sweden",
        "switzerland", "syria",

        # T
        "taiwan", "tajikistan", "tanzania", "thailand", "timor-leste",
        "east timor", "togo", "tonga", "trinidad and tobago", "tunisia",
        "turkey", "turkmenistan", "tuvalu",

        # U
        "uganda", "ukraine", "united arab emirates", "uae", "emirates", "dubai",
        "abu dhabi", "united kingdom", "uk", "britain", "england", "scotland",
        "wales", "northern ireland", "united states", "usa", "us", "america",
        "uruguay", "uzbekistan",

        # V
        "vanuatu", "vatican city", "vatican", "venezuela", "vietnam", "viet nam",

        # Y
        "yemen",

        # Z
        "zambia", "zimbabwe",

        # Common regions that are often treated as countries
        "hong kong", "macau", "puerto rico", "greenland",
    }

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
            "slot_ask_counts": state.slot_ask_counts,
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
            slot_ask_counts=data.get("slot_ask_counts", {}),
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

                # Clear last_asked_slot and reset ask count if we just filled it
                if key == state.last_asked_slot:
                    print(f"[SLOTS] Filled pending slot '{key}' with '{value}'")
                    state.last_asked_slot = None
                    # Reset ask count for this slot since it was successfully filled
                    state.slot_ask_counts[key] = 0

        # Validate ALL country-related slots across all intents
        # This prevents invalid country names (like "you-suggest", "all", etc.) from being stored

        # NO VALIDATION AT SLOT LEVEL
        # Slots are just data storage - accept whatever the LLM extracted
        # Intelligence and validation happens ONLY at URL generation
        # This allows the LLM to:
        # 1. See full context (even if "europe" is in slots)
        # 2. Handle naturally ("Which European country?")
        # 3. Not be blocked by premature validation

        # Just log what we have for debugging
        if intent == "country_to_country":
            origin = state.slots.get("origin_country", "")
            destination = state.slots.get("destination_country", "")
            print(f"[SLOTS] Stored: origin_country='{origin}', destination_country='{destination}'")

        if intent in ["search_trade_data", "search_country_data", "hs_code"]:
            country = state.slots.get("country", "")
            print(f"[SLOTS] Stored: country='{country}'")

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
        """
        Normalize country name to lowercase, URL-safe format.

        Note: This returns the canonical slug used internally.
        URL generation will map these to correct slugs per endpoint.
        """
        # Normalize to lowercase with hyphens
        normalized = value.lower().strip().replace(" ", "-")

        # Map common variations to canonical form (for slot storage consistency)
        # These will be mapped to actual URL slugs in generate_url()
        country_mapping = {
            "usa": "united-states",
            "us": "united-states",
            "america": "united-states",
            "americas": "united-states",
            "uk": "united-kingdom",
            "england": "united-kingdom",
            "britain": "united-kingdom",
            "great-britain": "united-kingdom",
            "korea": "south-korea",
            "holland": "netherlands",
            "uae": "united-arab-emirates",
        }

        return country_mapping.get(normalized, normalized)

    def is_continent(self, value: str) -> bool:
        """
        Check if the value is a continent (not a country).
        Continents should use KB data, not API calls.
        """
        if not value:
            return False
        normalized = value.lower().strip().replace("-", " ")
        return normalized in self.config.CONTINENTS

    def get_continent_name(self, value: str) -> str:
        """Get properly formatted continent name for display"""
        if not value:
            return ""
        normalized = value.lower().strip().replace("-", " ")

        # Map to proper display names
        continent_display = {
            "africa": "Africa",
            "asia": "Asia",
            "europe": "Europe",
            "north america": "North America",
            "south america": "South America",
            "oceania": "Oceania",
            "oceania australia": "Oceania Australia",
            "antarctica": "Antarctica",
            "america": "America",
            "asia pacific": "Asia Pacific",
            "global": "Global"
        }
        return continent_display.get(normalized, value.title())

    def is_restricted_country(self, value: str) -> bool:
        """
        Check if the country is restricted (requires demo/support).
        Restricted countries should not show data via API.
        """
        if not value:
            return False
        normalized = value.lower().strip().replace("-", " ")
        return normalized in self.config.RESTRICTED_COUNTRIES

    def get_restricted_country_name(self, value: str) -> str:
        """Get properly formatted restricted country name for display"""
        if not value:
            return ""
        return value.strip().replace("-", " ").title()

    def is_valid_country(self, value: str) -> bool:
        """
        Check if the value is a valid country name.
        Uses a hybrid approach:
        1. Check if in KNOWN_COUNTRIES list (fast path)
        2. If not, use heuristics to determine if it looks like a valid country name
        3. Reject obvious conversational phrases and invalid responses

        Args:
            value: Country name to validate (can be hyphenated or space-separated)

        Returns:
            True if likely a valid country, False if definitely not a country
        """
        if not value:
            return False

        # Normalize to match KNOWN_COUNTRIES format (lowercase, spaces not hyphens)
        # Strip common punctuation that users might accidentally include
        normalized = value.lower().strip().replace("-", " ")
        # Remove trailing punctuation like "?" or "!" that users might add
        normalized = normalized.rstrip('?!.,;:')
        # Remove leading prepositions like "for", "in", "from", "to"
        for prep in ["for ", "in ", "from ", "to ", "at ", "on "]:
            if normalized.startswith(prep):
                normalized = normalized[len(prep):].strip()

        # Fast path: Check if in known countries list
        if normalized in self.config.KNOWN_COUNTRIES:
            return True

        # Only reject OBVIOUS invalid inputs that definitely aren't countries
        # Let the LLM handle ambiguous cases naturally (regions, etc.)

        # Reject conversational phrases (obvious non-countries)
        conversational_phrases = [
            "you suggest", "suggest", "any", "anywhere",
            "everywhere", "all countries", "multiple", "many", "several",
            "which", "what", "where", "recommend", "best", "whatever",
            "dont care", "don't care", "idk", "i don't know",
            "dunno", "pick one", "choose", "decide", "up to you",
        ]
        if normalized in conversational_phrases:
            return False

        # Reject simple yes/no responses (obvious non-countries)
        invalid_responses = ["yes", "no", "ok", "okay", "sure", "maybe", "none", "nothing", "nope", "yep"]
        if normalized in invalid_responses:
            return False

        # Reject single letters or very short inputs (likely typos or abbreviations user doesn't want)
        if len(normalized) <= 2:
            return False

        # Reject numeric-only values
        if normalized.isdigit():
            return False

        # For URL generation: be strict - only allow known countries
        # For conversation: let LLM handle ambiguous inputs naturally
        # This validation is called before URL generation, so reject if not in known list

        # If it's not in KNOWN_COUNTRIES and not obviously invalid, reject for URL generation
        # but the LLM will still handle it naturally in conversation
        print(f"[SLOTS] '{value}' not in KNOWN_COUNTRIES list - will not generate URL")
        print(f"[SLOTS] LLM will handle this query naturally (may be region, typo, or needs clarification)")
        return False

    def is_complex_query(self, message: str, params: Dict[str, Any] = None) -> Tuple[bool, str]:
        """
        Detect if the query is complex and requires multiple API calls.

        Complex = needs data from 2+ specific countries (multiple API calls).
        NOT complex = general questions, single country queries, time ranges for one country.

        NOTE: country_to_country queries are NOT marked as complex since we have
        smart logic in _fix_url_data_type() to handle them intelligently based on
        whether both countries are mirror-only or if at least one has detailed data.

        Args:
            message: User's query message
            params: Extracted parameters from intent detection

        Returns:
            Tuple of (is_complex: bool, reason: str)
        """
        if not message:
            return False, ""

        # Check if this is a country_to_country intent
        # These are handled by smart mirror detection logic, not complex query handler
        if params and params.get("intent") == "country_to_country":
            print(f"  [COMPLEX] Skipping complex check for country_to_country intent (has smart mirror logic)")
            return False, ""

        message_lower = message.lower()

        # 1. Find all specific countries mentioned in the query
        countries_found = []
        for country in self.config.KNOWN_COUNTRIES:
            # Check for whole word match to avoid false positives
            pattern = r'\b' + re.escape(country) + r'\b'
            if re.search(pattern, message_lower):
                countries_found.append(country)

        # Only complex if 2+ specific countries are mentioned
        if len(countries_found) < 2:
            return False, ""

        # 2. Check for comparison keywords with multiple countries
        for keyword in self.config.COMPLEX_QUERY_PATTERNS["comparison_keywords"]:
            if keyword in message_lower:
                return True, f"comparing {' and '.join(countries_found[:2])}"

        # 3. Check for exclusion patterns with multiple countries
        for pattern in self.config.COMPLEX_QUERY_PATTERNS["exclusion_patterns"]:
            if pattern in message_lower:
                return True, f"comparing {' and '.join(countries_found[:2])}"

        # 4. Multiple countries mentioned = complex (needs 2+ API calls)
        return True, f"multi-country analysis: {', '.join(countries_found[:3])}"

    def get_complex_query_response(self, reason: str, query: str = "") -> Dict[str, Any]:
        """
        Generate response for complex queries that need dashboard access.

        Args:
            reason: Reason why the query is complex (e.g., "comparing usa and china")
            query: Original user query for context

        Returns:
            Response dict with message and actions
        """
        # Extract additional context from query
        query_lower = query.lower() if query else ""
        extra_context = []

        # Extract HS code if mentioned
        hs_match = re.search(r'hs\s*code\s*(\d+)', query_lower)
        if hs_match:
            extra_context.append(f"HS code {hs_match.group(1)}")

        # Extract product if mentioned
        product_keywords = ["copper", "steel", "electronics", "battery", "energy", "auto", "textile", "chemical", "pharmaceutical", "machinery", "plastic", "oil", "gas"]
        for product in product_keywords:
            if product in query_lower:
                extra_context.append(f"{product} products")
                break

        # Extract time range if mentioned
        time_match = re.search(r'(20\d{2})\s*[-–]\s*(20\d{2})', query_lower)
        if time_match:
            extra_context.append(f"{time_match.group(1)}-{time_match.group(2)} trends")

        # Build context string
        context_str = ""
        if extra_context:
            context_str = f" including {', '.join(extra_context)}"

        # Build message with query context
        message = (
            f"Great question! We have comprehensive data for {reason}{context_str}. "
            f"Our dashboard provides the detailed multi-country analysis you need. "
            f"Connect with our team to get full access:"
        )

        return {
            "message": message,
            "actions": [
                {"type": "schedule_demo", "label": "Schedule a Demo"},
                {"type": "chat_with_us", "label": "Talk to Live Agent"},
                {"type": "whatsapp", "label": "WhatsApp"},
                {"type": "continue_chat", "label": "Continue Chat"}
            ]
        }

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
        Includes loop detection - if we've asked for the same slot 3+ times,
        return a special response to trigger support options.

        Args:
            session_id: Session identifier
            intent: Query intent
            slots: Currently collected slots

        Returns:
            Dict with question info, special "too_many_attempts" marker, or None if no slots missing
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

        # Increment ask count for this slot
        if slot_name not in state.slot_ask_counts:
            state.slot_ask_counts[slot_name] = 0
        state.slot_ask_counts[slot_name] += 1

        ask_count = state.slot_ask_counts[slot_name]
        print(f"[SLOTS] Asking for slot '{slot_name}' (attempt {ask_count})")

        # Loop detection: If we've asked 3+ times, escalate to support
        if ask_count >= 3:
            print(f"[SLOTS] Loop detected: Asked for '{slot_name}' {ask_count} times. Escalating to support.")
            self._save_state(session_id, state)
            return {
                "slot_name": slot_name,
                "too_many_attempts": True,
                "message": f"I'm having trouble understanding the {definition.display_name.lower()}. Let me connect you with our team who can help you better:",
            }

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
            URL string, special marker for continents, or None if slots incomplete
            Returns "CONTINENT:{name}" for continent queries (use KB data instead of API)
        """
        if not self.has_all_required_slots(intent, slots):
            return None

        # Apply default values
        slots = self.get_slots_with_defaults(intent, slots)

        base_url = "https://www.marketinsidedata.com/en"

        if intent == "search_country_data":
            country = slots.get("country", "")

            # Check if this is a continent query (use KB data, not API)
            if self.is_continent(country):
                continent_name = self.get_continent_name(country)
                print(f"  [SLOTS] Detected continent query: {continent_name} - will use KB data")
                return f"CONTINENT:{continent_name}"

            # Check if this is a restricted country (redirect to support/demo)
            if self.is_restricted_country(country):
                country_name = self.get_restricted_country_name(country)
                print(f"  [SLOTS] Detected restricted country: {country_name} - redirect to support")
                return f"RESTRICTED:{country_name}"

            # Validate country before generating URL
            if not self.is_valid_country(country):
                print(f"  [SLOTS] Cannot generate URL: invalid country '{country}'")
                return None

            # Map canonical country name to URL slug for /country/ endpoint
            # /country/ uses short slugs: usa, uk, uae, etc.
            country_to_url_slug = {
                "united-states": "usa",
                "united-kingdom": "uk",
                "united-arab-emirates": "uae",
                "south-korea": "south-korea",
                # Other countries use their normalized form as-is
            }
            country_slug = country_to_url_slug.get(country, country)

            direction = slots.get("direction", "import")
            direction_suffix = "imports" if direction == "import" else "exports"
            return f"{base_url}/country/{country_slug}/{direction_suffix}"

        elif intent == "search_trade_data":
            country = slots.get("country", "")
            direction = slots.get("direction", "import")
            product = slots.get("product", "")
            hs_code = slots.get("hs_code", "")
            entity_type = slots.get("entity_type", "trade")

            # Validate country before generating URL (unless it's empty/universal)
            if country and country.lower() not in ["", "universal", "all"]:
                if not self.is_valid_country(country):
                    print(f"  [SLOTS] Cannot generate URL: invalid country '{country}' for search_trade_data")
                    return None

            # 🚨 CRITICAL BUSINESS LOGIC: Suppliers = Exporters, Buyers = Importers
            #
            # CORE RULE:
            # - When user asks for "suppliers" → Use /exporter endpoint (suppliers = exporters)
            # - When user asks for "buyers" → Use /importer endpoint (buyers = importers)
            #
            # URL Endpoints Available:
            # - /exporter?type=export = exporters/suppliers (they export/supply products)
            # - /importer?type=import = importers/buyers (they import/buy products)
            # - /trade?type={import|export} = general trade data

            if entity_type in ["exporters", "suppliers"]:
                # SUPPLIERS = EXPORTERS: Use exporter endpoint for both
                endpoint = "exporter"
                direction = "export"
            elif entity_type in ["importers", "buyers"]:
                # BUYERS = IMPORTERS: Use importer endpoint for both
                endpoint = "importer"
                direction = "import"
            else:
                # Default: use generic trade endpoint
                endpoint = "trade"

            # Format country with + for spaces (URL encoding) instead of hyphens
            country_formatted = country.replace("-", "+")
            params = f"type={direction}&country={country_formatted}"

            if product:
                params += f"&product={product.lower().replace(' ', '+')}"
            elif hs_code:
                params += f"&hs_code={hs_code}"

            return f"{base_url}/search-data/{endpoint}?{params}"

        elif intent == "country_to_country":
            origin = slots.get("origin_country", "")
            destination = slots.get("destination_country", "")
            direction = slots.get("direction", "export")

            # Validate both countries before generating URL
            if not self.is_valid_country(origin):
                print(f"  [SLOTS] Cannot generate URL: invalid origin_country '{origin}'")
                return None

            if not self.is_valid_country(destination):
                print(f"  [SLOTS] Cannot generate URL: invalid destination_country '{destination}'")
                return None

            # Convert to URL format (title case with %20 for spaces)
            origin_formatted = origin.title().replace("%20", " ").replace(" ", "%20")
            destination_formatted = destination.title().replace("%20", " ").replace(" ", "%20")

            return f"{base_url}/cntry/{origin_formatted}-{direction}-{destination_formatted}"

        elif intent == "hs_code":
            country = slots.get("country", "")
            direction = slots.get("direction", "import")
            hs_code = slots.get("hs_code", "")

            # Validate country before generating URL
            if not self.is_valid_country(country):
                print(f"  [SLOTS] Cannot generate URL: invalid country '{country}' for hs_code")
                return None

            # Map canonical country name to URL slug for /chapter/ endpoint
            # /chapter/ also uses short slugs: usa, uk, etc.
            country_to_url_slug = {
                "united-states": "usa",
                "united-kingdom": "uk",
                "united-arab-emirates": "uae",
                "south-korea": "south-korea",
            }
            country_slug = country_to_url_slug.get(country, country)

            # Zero-pad single-digit HS codes (e.g., "2" -> "02")
            # HS chapters are always 2 digits minimum
            if hs_code and len(hs_code) == 1 and hs_code.isdigit():
                hs_code = hs_code.zfill(2)

            return f"{base_url}/chapter/{country_slug}-{direction}-hs-code-{hs_code}"

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
