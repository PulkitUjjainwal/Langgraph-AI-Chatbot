"""
Smart Conversation History Manager

Handles conversation history with:
- Configurable context window (default 20 messages)
- Token-aware truncation
- Smart summarization for very long conversations
- Preservation of important context
"""

from typing import List, Dict, Any, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


class ConversationHistoryManager:
    """
    Manages conversation history with smart truncation and summarization

    Features:
    - Keeps recent N messages (configurable)
    - Respects character/token limits
    - Summarizes old messages if conversation is too long
    - Prioritizes recent messages
    """

    def __init__(
        self,
        max_messages: int = 20,
        max_chars: int = 4000,
        recent_to_keep: int = 6,
        enable_summarization: bool = True
    ):
        """
        Initialize history manager

        Args:
            max_messages: Maximum number of messages to keep
            max_chars: Maximum total characters for history
            recent_to_keep: Number of recent messages to always keep
            enable_summarization: Whether to summarize old messages
        """
        self.max_messages = max_messages
        self.max_chars = max_chars
        self.recent_to_keep = min(recent_to_keep, max_messages)
        self.enable_summarization = enable_summarization

    def _normalize_messages(self, messages: List) -> List[Dict[str, str]]:
        """
        Normalize messages to dict format

        Handles both:
        - LangChain messages (HumanMessage, AIMessage)
        - Dict format ({"role": "user", "content": "..."})

        Args:
            messages: List of messages (any format)

        Returns:
            List of normalized dict messages
        """
        conversation_messages = []

        for msg in messages:
            # Handle LangChain messages
            if isinstance(msg, HumanMessage):
                conversation_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                conversation_messages.append({"role": "assistant", "content": msg.content})
            # Handle dict format
            elif isinstance(msg, dict):
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role and content:
                    conversation_messages.append({"role": role, "content": content})

        return conversation_messages

    def build_history_text(self, messages: List[BaseMessage]) -> str:
        """
        Build formatted conversation history from messages

        Implements smart truncation:
        1. Keep last N messages (configurable)
        2. If still too long, summarize older messages
        3. Always preserve recent messages

        Args:
            messages: List of LangChain messages or dicts

        Returns:
            Formatted conversation history string
        """
        if not messages:
            return ""

        # Convert to dict format (handles both LangChain messages and dicts)
        conversation_messages = self._normalize_messages(messages)

        if not conversation_messages:
            return ""

        # Step 1: Keep only last max_messages
        if len(conversation_messages) > self.max_messages:
            conversation_messages = conversation_messages[-self.max_messages:]

        # Step 2: Format messages
        formatted_messages = []
        for msg in conversation_messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            formatted_messages.append(f"{role}: {msg['content']}")

        # Step 3: Check total length and truncate if needed
        full_history = "\n".join(formatted_messages)

        if len(full_history) <= self.max_chars:
            # Fits within limits - return as is
            return full_history

        # Step 4: Too long - apply smart truncation
        if self.enable_summarization and len(formatted_messages) > self.recent_to_keep:
            # Split into old and recent
            old_messages = formatted_messages[:-self.recent_to_keep]
            recent_messages = formatted_messages[-self.recent_to_keep:]

            # Summarize old messages
            summary = self._summarize_messages(old_messages)

            # Combine summary + recent messages
            result = f"[Earlier conversation summary: {summary}]\n\n" + "\n".join(recent_messages)

            # Final check - if still too long, just use recent messages
            if len(result) > self.max_chars:
                result = "\n".join(recent_messages)
                # Truncate from the beginning if still too long
                if len(result) > self.max_chars:
                    result = result[-self.max_chars:]

            return result
        else:
            # No summarization - just truncate recent messages
            # Keep as many recent messages as fit within char limit
            result = []
            char_count = 0

            for msg in reversed(formatted_messages):
                msg_len = len(msg) + 1  # +1 for newline
                if char_count + msg_len > self.max_chars:
                    break
                result.insert(0, msg)
                char_count += msg_len

            return "\n".join(result)

    def _summarize_messages(self, messages: List[str]) -> str:
        """
        Summarize a list of formatted messages

        For now, uses simple extraction of key information.
        Can be enhanced with LLM-based summarization later.

        Args:
            messages: List of formatted message strings

        Returns:
            Summary string
        """
        if not messages:
            return "No previous context"

        # Extract key information
        user_queries = []
        assistant_info = []

        for msg in messages:
            if msg.startswith("User:"):
                query = msg.replace("User:", "").strip()
                # Keep only first 50 chars of each query
                if len(query) > 50:
                    query = query[:47] + "..."
                user_queries.append(query)
            elif msg.startswith("Assistant:"):
                response = msg.replace("Assistant:", "").strip()
                # Extract any important entities (companies, countries, numbers)
                entities = self._extract_entities(response)
                if entities:
                    assistant_info.extend(entities)

        # Build summary
        parts = []

        if user_queries:
            # Keep up to 3 most recent queries
            recent_queries = user_queries[-3:]
            parts.append(f"User asked about: {'; '.join(recent_queries)}")

        if assistant_info:
            # Keep up to 5 most important entities
            unique_entities = list(dict.fromkeys(assistant_info))[:5]  # Remove duplicates, keep order
            parts.append(f"Discussed: {', '.join(unique_entities)}")

        summary = ". ".join(parts) if parts else f"{len(messages)} earlier messages"

        # Ensure summary itself isn't too long
        if len(summary) > 200:
            summary = summary[:197] + "..."

        return summary

    def _extract_entities(self, text: str) -> List[str]:
        """
        Extract important entities from text (simple version)

        Extracts:
        - Company names (capitalized words)
        - Countries (common trade countries)
        - Product categories

        Args:
            text: Text to extract from

        Returns:
            List of entity strings
        """
        entities = []
        text_lower = text.lower()

        # Common countries in trade
        countries = [
            'china', 'india', 'usa', 'mexico', 'brazil', 'germany',
            'japan', 'korea', 'indonesia', 'vietnam', 'thailand',
            'argentina', 'turkey', 'italy', 'france', 'spain'
        ]

        for country in countries:
            if country in text_lower:
                entities.append(country.title())

        # Common product categories
        products = [
            'electronics', 'textile', 'machinery', 'food', 'automotive',
            'chemicals', 'pharmaceutical', 'steel', 'plastic', 'furniture'
        ]

        for product in products:
            if product in text_lower:
                entities.append(product)

        return entities

    def get_message_count(self, messages: List[BaseMessage]) -> int:
        """
        Get count of user + assistant messages

        Args:
            messages: List of messages

        Returns:
            Count of conversation messages
        """
        count = 0
        for msg in messages:
            if isinstance(msg, (HumanMessage, AIMessage)):
                count += 1
        return count


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def build_conversation_history(
    messages: List[BaseMessage],
    max_messages: int = 20,
    max_chars: int = 4000,
    recent_to_keep: int = 6,
    enable_summarization: bool = True
) -> str:
    """
    Build conversation history with smart truncation

    Convenience function that creates a manager and builds history.

    Args:
        messages: List of messages
        max_messages: Maximum messages to keep
        max_chars: Maximum total characters
        recent_to_keep: Recent messages to always keep
        enable_summarization: Whether to summarize old messages

    Returns:
        Formatted conversation history string
    """
    manager = ConversationHistoryManager(
        max_messages=max_messages,
        max_chars=max_chars,
        recent_to_keep=recent_to_keep,
        enable_summarization=enable_summarization
    )
    return manager.build_history_text(messages)


def build_conversation_history_from_settings(
    messages: List[BaseMessage],
    settings: Optional[Any] = None
) -> str:
    """
    Build conversation history using configuration from settings

    Args:
        messages: List of messages
        settings: Settings object (if None, uses defaults)

    Returns:
        Formatted conversation history string
    """
    if settings is None:
        # Use defaults
        return build_conversation_history(messages)

    manager = ConversationHistoryManager(
        max_messages=getattr(settings, 'max_history_messages', 20),
        max_chars=getattr(settings, 'max_history_chars', 4000),
        recent_to_keep=getattr(settings, 'recent_messages_to_keep', 6),
        enable_summarization=getattr(settings, 'enable_history_summarization', True)
    )
    return manager.build_history_text(messages)
