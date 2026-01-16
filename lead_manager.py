"""
Lead Generation Manager for Chatbot

Handles lead capture logic:
- Determines when to prompt for lead info
- Validates and stores lead data in Redis
- Manages prompt cooldowns and skip logic
"""

import re
import json
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime


class LeadManager:
    """
    Manages lead capture and storage

    Features:
    - Smart trigger detection (high-intent keywords, engagement threshold)
    - Cooldown between prompts (respects user's "maybe later")
    - Maximum prompt limit (stops after 3 attempts)
    - Redis-based persistence with 30-day TTL
    """

    # Configuration
    MAX_PROMPTS = 3                    # Maximum times to prompt per session
    COOLDOWN_MESSAGES = 4              # Messages to wait after skip
    ENGAGEMENT_THRESHOLD = 3           # Messages before first prompt
    LEAD_TTL_DAYS = 30                 # Days to keep lead data

    # High-intent keywords that trigger lead prompt
    HIGH_INTENT_KEYWORDS = [
        'buyers', 'buyer', 'suppliers', 'supplier',
        'contact', 'contacts', 'email', 'phone',
        'download', 'export', 'send me', 'send it',
        'api', 'pricing', 'price', 'cost', 'quote',
        'list of', 'names of', 'all the', 'complete list',
        'get access', 'full data', 'detailed report'
    ]

    # Prompt messages based on trigger type
    PROMPT_MESSAGES = {
        "high_intent": "I can send you this detailed information directly. What's your email?",
        "engagement": "I'm happy to help! To send you a summary of our conversation, could you share your email?",
        "data_request": "I can email you this complete report with all the details. What's your email address?",
        "reminder": "Quick reminder - want me to send these insights to your inbox?",
        "final": "Would you like me to email you these trade insights before you go?"
    }

    def __init__(self, redis_manager):
        """
        Initialize LeadManager with Redis connection

        Args:
            redis_manager: RedisMemoryManager instance
        """
        self.redis = redis_manager
        self.ttl_seconds = self.LEAD_TTL_DAYS * 24 * 3600
        print("[OK] LeadManager initialized")

    # =========================================================================
    # LEAD PROMPT LOGIC
    # =========================================================================

    def should_prompt_for_lead(
        self,
        session_id: str,
        message: str,
        message_count: int = 0
    ) -> Tuple[bool, str, str]:
        """
        Determine if we should prompt for lead info

        Args:
            session_id: Session identifier
            message: Current user message
            message_count: Number of messages in conversation

        Returns:
            Tuple of (should_prompt, prompt_type, prompt_message)
        """
        # 1. Already captured lead? Never prompt again
        if self.get_lead(session_id):
            return False, "", ""

        # 2. Get session lead metadata
        meta = self._get_lead_meta(session_id)
        prompt_count = meta.get("prompt_count", 0)
        last_prompted_at = meta.get("last_prompted_at", 0)

        # 3. Max prompts reached? Stop asking
        if prompt_count >= self.MAX_PROMPTS:
            return False, "", ""

        # 4. In cooldown period? Wait before asking again
        if prompt_count > 0:
            messages_since_prompt = message_count - last_prompted_at
            if messages_since_prompt < self.COOLDOWN_MESSAGES:
                return False, "", ""

        # 5. Check trigger conditions
        message_lower = message.lower()

        # High-intent keyword detection
        has_high_intent = any(kw in message_lower for kw in self.HIGH_INTENT_KEYWORDS)

        if has_high_intent:
            prompt_type = "high_intent"
            if prompt_count == 0:
                prompt_message = self.PROMPT_MESSAGES["high_intent"]
            elif prompt_count == 1:
                prompt_message = self.PROMPT_MESSAGES["reminder"]
            else:
                prompt_message = self.PROMPT_MESSAGES["final"]
            return True, prompt_type, prompt_message

        # Engagement threshold (first prompt only)
        if prompt_count == 0 and message_count >= self.ENGAGEMENT_THRESHOLD:
            return True, "engagement", self.PROMPT_MESSAGES["engagement"]

        # Subsequent prompts need high intent or more engagement
        if prompt_count > 0 and message_count >= last_prompted_at + self.COOLDOWN_MESSAGES + 2:
            if prompt_count == 1:
                return True, "reminder", self.PROMPT_MESSAGES["reminder"]
            else:
                return True, "final", self.PROMPT_MESSAGES["final"]

        return False, "", ""

    def record_prompt(self, session_id: str, message_count: int, prompt_type: str):
        """
        Record that a lead prompt was shown

        Args:
            session_id: Session identifier
            message_count: Current message count
            prompt_type: Type of prompt shown
        """
        meta = self._get_lead_meta(session_id)
        meta["prompt_count"] = meta.get("prompt_count", 0) + 1
        meta["last_prompted_at"] = message_count
        meta["last_prompt_type"] = prompt_type
        meta["last_prompt_time"] = datetime.now().isoformat()
        self._save_lead_meta(session_id, meta)

    def record_skip(self, session_id: str):
        """
        Record that user skipped the lead form

        Args:
            session_id: Session identifier
        """
        meta = self._get_lead_meta(session_id)
        meta["skipped"] = True
        meta["skip_count"] = meta.get("skip_count", 0) + 1
        meta["last_skip_time"] = datetime.now().isoformat()
        self._save_lead_meta(session_id, meta)

    # =========================================================================
    # LEAD DATA MANAGEMENT
    # =========================================================================

    def save_lead(
        self,
        session_id: str,
        email: str,
        phone: Optional[str] = None,
        company_name: Optional[str] = None,
        name: Optional[str] = None,
        source_url: Optional[str] = None,
        extra_data: Optional[Dict] = None
    ) -> Tuple[bool, str]:
        """
        Save lead information to Redis

        Args:
            session_id: Session identifier
            email: User's email (required)
            phone: User's phone (optional)
            company_name: User's company (optional)
            name: User's name (optional)
            source_url: Page URL where lead was captured
            extra_data: Additional metadata

        Returns:
            Tuple of (success, message)
        """
        # Validate email
        if not self._validate_email(email):
            return False, "Invalid email format"

        # Validate phone if provided
        if phone and not self._validate_phone(phone):
            return False, "Invalid phone number format"

        # Build lead data
        lead_data = {
            "email": email.strip().lower(),
            "phone": self._clean_phone(phone) if phone else None,
            "company_name": company_name.strip() if company_name else None,
            "name": name.strip() if name else None,
            "session_id": session_id,
            "source_url": source_url,
            "captured_at": datetime.now().isoformat(),
            "extra_data": extra_data or {}
        }

        # Get lead metadata for context
        meta = self._get_lead_meta(session_id)
        lead_data["prompt_count_before_capture"] = meta.get("prompt_count", 0)
        lead_data["trigger_type"] = meta.get("last_prompt_type", "unknown")

        # Save to Redis
        key = f"lead:{session_id}"
        try:
            self.redis.client.setex(
                key,
                self.ttl_seconds,
                json.dumps(lead_data)
            )

            # Update metadata
            meta["captured"] = True
            meta["captured_at"] = lead_data["captured_at"]
            self._save_lead_meta(session_id, meta)

            # Also add to leads list for easy retrieval
            self._add_to_leads_list(session_id, email)

            print(f"[LEAD] Captured lead for session {session_id}: {email}")
            return True, "Lead captured successfully"

        except Exception as e:
            print(f"[ERROR] Failed to save lead: {e}")
            return False, f"Failed to save lead: {str(e)}"

    def get_lead(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get lead info for a session

        Args:
            session_id: Session identifier

        Returns:
            Lead data dict or None
        """
        key = f"lead:{session_id}"
        try:
            data = self.redis.client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"[ERROR] Failed to get lead: {e}")
        return None

    def get_all_leads(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all captured leads (admin function)

        Args:
            limit: Maximum number of leads to return

        Returns:
            List of lead data dicts
        """
        leads = []
        try:
            # Get from leads list
            list_key = "leads:all"
            lead_refs = self.redis.client.lrange(list_key, 0, limit - 1)

            for ref in lead_refs:
                ref_data = json.loads(ref)
                session_id = ref_data.get("session_id")
                if session_id:
                    lead = self.get_lead(session_id)
                    if lead:
                        leads.append(lead)
        except Exception as e:
            print(f"[ERROR] Failed to get all leads: {e}")

        return leads

    def get_lead_stats(self) -> Dict[str, Any]:
        """
        Get lead capture statistics

        Returns:
            Dict with lead statistics
        """
        try:
            # Count lead keys
            lead_keys = list(self.redis.client.scan_iter(match="lead:*", count=1000))
            lead_count = len([k for k in lead_keys if b":meta" not in k])

            return {
                "total_leads": lead_count,
                "retrieved_at": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"[ERROR] Failed to get lead stats: {e}")
            return {"total_leads": 0, "error": str(e)}

    # =========================================================================
    # VALIDATION HELPERS
    # =========================================================================

    def _validate_email(self, email: str) -> bool:
        """Validate email format"""
        if not email:
            return False
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email.strip()))

    def _validate_phone(self, phone: str) -> bool:
        """Validate phone number (at least 10 digits)"""
        if not phone:
            return True  # Optional field
        digits = re.sub(r'[^\d]', '', phone)
        return len(digits) >= 10

    def _clean_phone(self, phone: str) -> str:
        """Clean phone number, keep only digits and +"""
        if not phone:
            return ""
        # Keep + at start if present, then only digits
        cleaned = re.sub(r'[^\d+]', '', phone)
        # Ensure + is only at the start
        if '+' in cleaned:
            cleaned = '+' + cleaned.replace('+', '')
        return cleaned

    # =========================================================================
    # REDIS HELPERS
    # =========================================================================

    def _get_lead_meta(self, session_id: str) -> Dict[str, Any]:
        """Get lead metadata for session"""
        key = f"lead:{session_id}:meta"
        try:
            data = self.redis.client.get(key)
            if data:
                return json.loads(data)
        except Exception:
            pass
        return {}

    def _save_lead_meta(self, session_id: str, meta: Dict[str, Any]):
        """Save lead metadata for session"""
        key = f"lead:{session_id}:meta"
        try:
            self.redis.client.setex(
                key,
                self.ttl_seconds,
                json.dumps(meta)
            )
        except Exception as e:
            print(f"[ERROR] Failed to save lead meta: {e}")

    def _add_to_leads_list(self, session_id: str, email: str):
        """Add lead to global leads list for easy retrieval"""
        list_key = "leads:all"
        try:
            ref_data = {
                "session_id": session_id,
                "email": email,
                "captured_at": datetime.now().isoformat()
            }
            self.redis.client.lpush(list_key, json.dumps(ref_data))
            # Keep only last 10000 leads in list
            self.redis.client.ltrim(list_key, 0, 9999)
        except Exception as e:
            print(f"[ERROR] Failed to add to leads list: {e}")


def get_lead_form_config(prompt_type: str, prompt_message: str) -> Dict[str, Any]:
    """
    Get lead form configuration for frontend

    Args:
        prompt_type: Type of trigger (high_intent, engagement, etc.)
        prompt_message: Message to show user

    Returns:
        Dict with form configuration
    """
    return {
        "show_form": True,
        "prompt_type": prompt_type,
        "message": prompt_message,
        "fields": [
            {
                "name": "email",
                "type": "email",
                "label": "Email",
                "placeholder": "your@email.com",
                "required": True
            },
            {
                "name": "phone",
                "type": "tel",
                "label": "Phone",
                "placeholder": "+1 234 567 8900",
                "required": False
            },
            {
                "name": "company_name",
                "type": "text",
                "label": "Company",
                "placeholder": "Your Company",
                "required": False
            }
        ],
        "buttons": {
            "submit": "Send to my email",
            "skip": "Maybe later"
        }
    }
