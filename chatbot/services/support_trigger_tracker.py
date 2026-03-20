"""
Support Trigger Tracker - Frequency control for support option display

Prevents overwhelming users by limiting how often support options are shown.
Uses Redis for session-scoped tracking with 24-hour TTL.
"""

import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class SupportTriggerTracker:
    """
    Tracks support option triggers per session to avoid overwhelming users.

    Thresholds:
    - Max 3 support prompts per session
    - Min 2 messages between support prompts
    - Cooldown: 5 minutes between identical trigger types
    """

    # Redis key prefix
    REDIS_KEY_PREFIX = "session:support_triggers:"

    # Thresholds
    MAX_TRIGGERS_PER_SESSION = 3
    MIN_MESSAGE_SPACING = 2
    COOLDOWN_SECONDS = 300  # 5 minutes

    # TTL for Redis keys (24 hours)
    TTL_SECONDS = 24 * 3600

    def __init__(self, redis_manager=None):
        """
        Initialize tracker with optional Redis manager.

        Args:
            redis_manager: RedisMemoryManager instance (optional - falls back to in-memory)
        """
        self.redis = redis_manager
        self._memory_store: Dict[str, List[Dict]] = {}  # Fallback in-memory storage

    def should_show_support(
        self,
        session_id: str,
        trigger_type: str,
        current_message_count: int
    ) -> Tuple[bool, str]:
        """
        Determine if support options should be shown.

        Args:
            session_id: User session ID
            trigger_type: Type of trigger (e.g., "service_scope_mismatch")
            current_message_count: Current number of messages in conversation

        Returns:
            Tuple of (should_show, reason_if_not)
            - should_show: True if support can be shown
            - reason_if_not: Empty string if allowed, otherwise reason for blocking
        """
        try:
            triggers = self._get_triggers(session_id)

            # Check threshold 1: Max triggers per session
            if len(triggers) >= self.MAX_TRIGGERS_PER_SESSION:
                logger.info(f"[SUPPORT_TRACKER] Session {session_id}: Max triggers reached ({self.MAX_TRIGGERS_PER_SESSION})")
                return False, "max_triggers_reached"

            # Check threshold 2: Message spacing
            if triggers:
                last_trigger_count = triggers[-1].get("message_count", 0)
                messages_since_last = current_message_count - last_trigger_count

                if messages_since_last < self.MIN_MESSAGE_SPACING:
                    logger.info(f"[SUPPORT_TRACKER] Session {session_id}: Too soon (spacing: {messages_since_last} < {self.MIN_MESSAGE_SPACING})")
                    return False, "too_soon_message_spacing"

            # Check threshold 3: Cooldown for same type
            now = datetime.now()
            recent_same_type = [
                t for t in triggers
                if t.get("type") == trigger_type
                and (now - datetime.fromisoformat(t.get("timestamp", "1970-01-01"))).total_seconds() < self.COOLDOWN_SECONDS
            ]

            if recent_same_type:
                logger.info(f"[SUPPORT_TRACKER] Session {session_id}: Cooldown active for type '{trigger_type}'")
                return False, "cooldown_active"

            logger.info(f"[SUPPORT_TRACKER] Session {session_id}: Support allowed (triggers: {len(triggers)}/{self.MAX_TRIGGERS_PER_SESSION})")
            return True, ""

        except Exception as e:
            logger.error(f"[SUPPORT_TRACKER] Error checking threshold: {e}")
            # Fail open - allow support on error
            return True, ""

    def record_trigger(
        self,
        session_id: str,
        trigger_type: str,
        message_count: int
    ) -> bool:
        """
        Record that support was shown.

        Args:
            session_id: User session ID
            trigger_type: Type of trigger
            message_count: Message count when triggered

        Returns:
            True if recorded successfully
        """
        try:
            triggers = self._get_triggers(session_id)

            # Add new trigger
            new_trigger = {
                "type": trigger_type,
                "timestamp": datetime.now().isoformat(),
                "message_count": message_count
            }
            triggers.append(new_trigger)

            # Save back to storage
            self._save_triggers(session_id, triggers)

            logger.info(f"[SUPPORT_TRACKER] Session {session_id}: Recorded trigger '{trigger_type}' at message {message_count} (total: {len(triggers)})")
            return True

        except Exception as e:
            logger.error(f"[SUPPORT_TRACKER] Error recording trigger: {e}")
            return False

    def get_trigger_count(self, session_id: str) -> int:
        """Get number of support triggers for this session."""
        try:
            return len(self._get_triggers(session_id))
        except Exception as e:
            logger.error(f"[SUPPORT_TRACKER] Error getting trigger count: {e}")
            return 0

    def reset_session(self, session_id: str) -> bool:
        """Reset support triggers for a session (for testing)."""
        try:
            if self.redis:
                key = f"{self.REDIS_KEY_PREFIX}{session_id}"
                self.redis.redis_client.delete(key)
            else:
                self._memory_store.pop(session_id, None)

            logger.info(f"[SUPPORT_TRACKER] Session {session_id}: Reset triggers")
            return True
        except Exception as e:
            logger.error(f"[SUPPORT_TRACKER] Error resetting session: {e}")
            return False

    def _get_triggers(self, session_id: str) -> List[Dict]:
        """
        Get existing triggers from storage.

        Returns:
            List of trigger dicts with keys: type, timestamp, message_count
        """
        try:
            if self.redis:
                # Try Redis first
                key = f"{self.REDIS_KEY_PREFIX}{session_id}"
                data = self.redis.redis_client.get(key)

                if data:
                    triggers = json.loads(data)
                    if isinstance(triggers, list):
                        return triggers

                return []
            else:
                # Fallback to in-memory
                return self._memory_store.get(session_id, [])

        except Exception as e:
            logger.error(f"[SUPPORT_TRACKER] Error getting triggers: {e}")
            return []

    def _save_triggers(self, session_id: str, triggers: List[Dict]) -> bool:
        """
        Save triggers to storage.

        Args:
            session_id: User session ID
            triggers: List of trigger dicts

        Returns:
            True if saved successfully
        """
        try:
            if self.redis:
                # Save to Redis with TTL
                key = f"{self.REDIS_KEY_PREFIX}{session_id}"
                data = json.dumps(triggers)
                self.redis.redis_client.setex(key, self.TTL_SECONDS, data)
            else:
                # Fallback to in-memory
                self._memory_store[session_id] = triggers

            return True

        except Exception as e:
            logger.error(f"[SUPPORT_TRACKER] Error saving triggers: {e}")
            return False


# Singleton instance
_support_trigger_tracker: Optional[SupportTriggerTracker] = None


def get_support_trigger_tracker(redis_manager=None) -> SupportTriggerTracker:
    """
    Get singleton instance of SupportTriggerTracker.

    Args:
        redis_manager: RedisMemoryManager instance (optional)

    Returns:
        SupportTriggerTracker instance
    """
    global _support_trigger_tracker

    if _support_trigger_tracker is None:
        _support_trigger_tracker = SupportTriggerTracker(redis_manager)

    return _support_trigger_tracker
