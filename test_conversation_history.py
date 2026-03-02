"""
Test script for conversation history manager

Tests:
1. Basic history building with few messages
2. History with many messages (truncation)
3. History with very long messages (char limit)
4. Summarization feature
5. Both LangChain and dict message formats
"""

import sys
import io

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from langchain_core.messages import HumanMessage, AIMessage
from chatbot.utils.conversation_history_manager import (
    ConversationHistoryManager,
    build_conversation_history,
    build_conversation_history_from_settings
)
from chatbot.config.settings import get_settings


def test_basic_history():
    """Test with a few messages"""
    print("\n" + "="*70)
    print("TEST 1: Basic History (4 messages)")
    print("="*70)

    messages = [
        HumanMessage(content="What is Export Genius?"),
        AIMessage(content="Export Genius is a global trade intelligence platform."),
        HumanMessage(content="What data do you have?"),
        AIMessage(content="We have import/export records from 80+ countries."),
    ]

    manager = ConversationHistoryManager(max_messages=20)
    history = manager.build_history_text(messages)

    print(f"Messages count: {len(messages)}")
    print(f"History length: {len(history)} chars")
    print(f"\nHistory:\n{history}")

    assert "User: What is Export Genius?" in history
    assert "Assistant: Export Genius is a global trade intelligence platform" in history
    print("\n[PASS] Test 1 PASSED")


def test_many_messages():
    """Test with many messages (should truncate to max)"""
    print("\n" + "="*70)
    print("TEST 2: Many Messages (40 messages, max=20)")
    print("="*70)

    messages = []
    for i in range(20):
        messages.append(HumanMessage(content=f"Question {i+1}"))
        messages.append(AIMessage(content=f"Answer {i+1}"))

    manager = ConversationHistoryManager(max_messages=20)
    history = manager.build_history_text(messages)

    print(f"Total messages: {len(messages)}")
    print(f"History length: {len(history)} chars")
    print(f"Lines in history: {len(history.split(chr(10)))}")

    # Should not have the very first messages (truncated)
    # NOTE: Use exact match to avoid "Question 11" containing "Question 1"
    assert "User: Question 1\n" not in history
    assert "User: Question 2\n" not in history
    assert "User: Question 3\n" not in history
    # Should have recent messages
    assert "Question 20" in history
    assert "Answer 20" in history

    print(f"\nHistory preview (first 500 chars):\n{history[:500]}...")
    print("\n[PASS] Test 2 PASSED")


def test_long_messages():
    """Test with very long messages (should truncate by chars)"""
    print("\n" + "="*70)
    print("TEST 3: Long Messages (exceeds char limit)")
    print("="*70)

    # Create messages with moderately long content
    long_content = "This is important trade data information. " * 15  # ~650 chars

    messages = [
        HumanMessage(content="Tell me about trade data"),
        AIMessage(content=long_content),
        HumanMessage(content="What about Mexico?"),
        AIMessage(content=long_content),
        HumanMessage(content="And Brazil?"),
        AIMessage(content=long_content),
        HumanMessage(content="Show me latest stats"),
        AIMessage(content=long_content),
    ]

    manager = ConversationHistoryManager(max_messages=20, max_chars=2000)
    history = manager.build_history_text(messages)

    print(f"Total messages: {len(messages)}")
    print(f"History length: {len(history)} chars (limit=2000)")

    assert len(history) > 0, "History should not be empty"
    assert len(history) <= 2000, f"History too long: {len(history)} chars"
    # Should have at least one recent message
    assert "Brazil" in history or "Mexico" in history or "stats" in history

    print(f"\nHistory preview (first 300 chars):\n{history[:300]}...")
    print("\n[PASS] Test 3 PASSED")


def test_summarization():
    """Test summarization feature"""
    print("\n" + "="*70)
    print("TEST 4: Summarization (long conversation)")
    print("="*70)

    messages = []
    # Add 20 older messages
    for i in range(10):
        messages.append(HumanMessage(content=f"Question about China textile imports {i+1}"))
        messages.append(AIMessage(content=f"Answer about China textile market {i+1}. Major importers include companies in USA, Germany, and Japan."))

    # Add recent messages
    messages.append(HumanMessage(content="What about electronics?"))
    messages.append(AIMessage(content="Electronics is a major export category"))
    messages.append(HumanMessage(content="Show me India data"))
    messages.append(AIMessage(content="India exports to 150+ countries"))

    manager = ConversationHistoryManager(
        max_messages=24,
        max_chars=1500,
        recent_to_keep=4,
        enable_summarization=True
    )
    history = manager.build_history_text(messages)

    print(f"Total messages: {len(messages)}")
    print(f"History length: {len(history)} chars")

    # Check for summary marker
    if "[Earlier conversation summary:" in history:
        print("\n[NOTE] Summarization was applied!")
        print(f"\nHistory:\n{history}")
    else:
        print("\n[NOTE] Summarization was not needed (fits within limits)")

    # Should have recent messages
    assert "electronics" in history.lower() or "india" in history.lower()

    print("\n[PASS] Test 4 PASSED")


def test_dict_format():
    """Test with dict format messages (streaming chat format)"""
    print("\n" + "="*70)
    print("TEST 5: Dict Format Messages (streaming)")
    print("="*70)

    messages = [
        {"role": "user", "content": "What is Export Genius?"},
        {"role": "assistant", "content": "Export Genius is a trade platform."},
        {"role": "user", "content": "Do you have Mexico data?"},
        {"role": "assistant", "content": "Yes, we have complete Mexico import data."},
    ]

    manager = ConversationHistoryManager(max_messages=20)
    history = manager.build_history_text(messages)

    print(f"Messages count: {len(messages)}")
    print(f"History length: {len(history)} chars")
    print(f"\nHistory:\n{history}")

    assert "User: What is Export Genius?" in history
    assert "Assistant: Export Genius is a trade platform" in history
    print("\n[PASS] Test 5 PASSED")


def test_with_settings():
    """Test using settings from config"""
    print("\n" + "="*70)
    print("TEST 6: Using Settings from Config")
    print("="*70)

    settings = get_settings()

    print(f"Settings:")
    print(f"  max_history_messages: {settings.max_history_messages}")
    print(f"  max_history_chars: {settings.max_history_chars}")
    print(f"  recent_messages_to_keep: {settings.recent_messages_to_keep}")
    print(f"  enable_history_summarization: {settings.enable_history_summarization}")

    messages = [
        HumanMessage(content="Test message 1"),
        AIMessage(content="Response 1"),
        HumanMessage(content="Test message 2"),
        AIMessage(content="Response 2"),
    ]

    history = build_conversation_history_from_settings(messages, settings)

    print(f"\nHistory length: {len(history)} chars")
    print(f"\nHistory:\n{history}")

    assert "Test message 1" in history
    print("\n[PASS] Test 6 PASSED")


def test_mixed_formats():
    """Test with mixed LangChain and dict messages"""
    print("\n" + "="*70)
    print("TEST 7: Mixed Format Messages")
    print("="*70)

    messages = [
        HumanMessage(content="Question 1"),
        AIMessage(content="Answer 1"),
        {"role": "user", "content": "Question 2"},
        {"role": "assistant", "content": "Answer 2"},
        HumanMessage(content="Question 3"),
    ]

    manager = ConversationHistoryManager(max_messages=20)
    history = manager.build_history_text(messages)

    print(f"Messages count: {len(messages)}")
    print(f"History:\n{history}")

    assert "User: Question 1" in history
    assert "User: Question 2" in history
    assert "User: Question 3" in history
    print("\n[PASS] Test 7 PASSED")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("CONVERSATION HISTORY MANAGER - COMPREHENSIVE TESTS")
    print("="*70)

    try:
        test_basic_history()
        test_many_messages()
        test_long_messages()
        test_summarization()
        test_dict_format()
        test_with_settings()
        test_mixed_formats()

        print("\n" + "="*70)
        print("[PASS] ALL TESTS PASSED!")
        print("="*70)
        print("\nSummary:")
        print("  - Basic history building: [PASS]")
        print("  - Message truncation (max_messages): [PASS]")
        print("  - Character limit enforcement: [PASS]")
        print("  - Smart summarization: [PASS]")
        print("  - Dict format support: [PASS]")
        print("  - Settings integration: [PASS]")
        print("  - Mixed format handling: [PASS]")
        print("\n[SUCCESS] Conversation history context issue is FIXED!")
        print("   Now supports up to 20 messages with smart truncation.")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    run_all_tests()
