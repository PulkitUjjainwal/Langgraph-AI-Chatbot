"""
Test User Flow Fixes

Tests for two critical UX issues:
1. "You suggest" being treated as a country name
2. Single-word country answers (like "CHINA") changing intent incorrectly
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chatbot.services.slot_manager import SlotManager


def test_you_suggest_rejection():
    """
    Test Issue 1: "You suggest" should be rejected as invalid country

    Scenario:
    - User asks about polyester resins buyers
    - System asks for country
    - User says "You suggest"
    - System should reject it and ask again (not create URL with "you-suggest")
    """
    print("=" * 70)
    print("TEST 1: 'You suggest' Rejection")
    print("=" * 70)
    print()

    sm = SlotManager(redis_manager=None)
    session_id = "test_you_suggest"

    # Step 1: Initial query with missing country
    print("Step 1: User asks about polyester resins buyers (missing country)")
    params1 = {
        "product": "polyester%20resins",
        "entity_type": "buyers",
        "direction": "import"
    }
    state1 = sm.update_slots(session_id, "search_trade_data", params1)
    print(f"  Slots: {state1.slots}")
    print(f"  Missing: {state1.missing_slots}")
    print(f"  Should ask for: country")
    print()

    # Step 2: User responds "You suggest"
    print("Step 2: User says 'You suggest'")
    params2 = {"country": "you suggest"}  # Simulating what would be extracted
    state2 = sm.update_slots(session_id, "search_trade_data", params2)
    print(f"  Slots after validation: {state2.slots}")
    print(f"  Missing after validation: {state2.missing_slots}")
    print(f"  last_asked_slot: {state2.last_asked_slot}")

    # Verify
    test1 = "country" not in state2.slots  # Should be rejected
    test2 = "country" in state2.missing_slots  # Should be marked as missing
    test3 = state2.last_asked_slot == "country"  # Should be pending for next answer

    print(f"  [{'PASS' if test1 else 'FAIL'}] 'you suggest' rejected: {test1}")
    print(f"  [{'PASS' if test2 else 'FAIL'}] 'country' marked as missing: {test2}")
    print(f"  [{'PASS' if test3 else 'FAIL'}] 'country' marked as pending: {test3}")
    print()

    # Step 3: Try to generate URL (should fail)
    print("Step 3: URL generation attempt")
    url = sm.generate_url("search_trade_data", state2.slots)
    test4 = url is None
    print(f"  Generated URL: {url}")
    print(f"  [{'PASS' if test4 else 'FAIL'}] URL is None: {test4}")
    print()

    sm.clear_slots(session_id)

    if all([test1, test2, test3, test4]):
        print("✓ TEST 1 PASSED: 'You suggest' is properly rejected")
    else:
        print("✗ TEST 1 FAILED")
    print()
    return all([test1, test2, test3, test4])


def test_china_slot_fill():
    """
    Test Issue 2: "CHINA" after "You suggest" should fill the slot, not change intent

    Scenario:
    - User asks about polyester resins buyers
    - System asks for country
    - User says "You suggest" (rejected, slot pending)
    - User says "CHINA" - should be treated as slot fill, not new query
    """
    print("=" * 70)
    print("TEST 2: 'CHINA' Slot Fill (Maintaining Context)")
    print("=" * 70)
    print()

    sm = SlotManager(redis_manager=None)
    session_id = "test_china_fill"

    # Step 1: Initial query
    print("Step 1: User asks about polyester resins buyers")
    params1 = {
        "product": "polyester%20resins",
        "entity_type": "buyers",
        "direction": "import"
    }
    state1 = sm.update_slots(session_id, "search_trade_data", params1)
    print(f"  Intent: {state1.intent}")
    print(f"  Slots: {state1.slots}")
    print()

    # Step 2: User says "You suggest" (gets rejected)
    print("Step 2: User says 'You suggest' (rejected)")
    params2 = {"country": "you suggest"}
    state2 = sm.update_slots(session_id, "search_trade_data", params2)
    print(f"  last_asked_slot after rejection: {state2.last_asked_slot}")
    print(f"  This slot is now pending for next answer")
    print()

    # Step 3: User says "CHINA"
    # In real flow, this would be detected as slot answer because last_asked_slot = "country"
    # We're simulating what happens when slot answer detection works
    print("Step 3: User says 'CHINA'")
    print("  (In real flow, detected as slot answer for 'country')")
    params3 = {"country": "china"}
    state3 = sm.update_slots(session_id, "search_trade_data", params3)

    print(f"  Intent: {state3.intent}")
    print(f"  Slots: {state3.slots}")
    print(f"  Missing: {state3.missing_slots}")

    # Verify
    test1 = state3.intent == "search_trade_data"  # Intent should stay the same
    test2 = state3.slots.get("country") == "china"  # China should be accepted
    test3 = state3.slots.get("product") == "polyester%20resins"  # Product context preserved
    test4 = len(state3.missing_slots) == 0  # All slots filled

    print(f"  [{'PASS' if test1 else 'FAIL'}] Intent maintained (search_trade_data): {test1}")
    print(f"  [{'PASS' if test2 else 'FAIL'}] China accepted: {test2}")
    print(f"  [{'PASS' if test3 else 'FAIL'}] Product context preserved: {test3}")
    print(f"  [{'PASS' if test4 else 'FAIL'}] All slots filled: {test4}")
    print()

    # Step 4: Generate URL (should succeed with china + polyester resins)
    print("Step 4: URL generation")
    url = sm.generate_url("search_trade_data", state3.slots)
    print(f"  Generated URL: {url}")

    test5 = url is not None
    test6 = "china" in url.lower() if url else False
    test7 = "polyester" in url.lower() if url else False

    print(f"  [{'PASS' if test5 else 'FAIL'}] URL generated: {test5}")
    print(f"  [{'PASS' if test6 else 'FAIL'}] URL contains 'china': {test6}")
    print(f"  [{'PASS' if test7 else 'FAIL'}] URL contains 'polyester': {test7}")
    print()

    sm.clear_slots(session_id)

    if all([test1, test2, test3, test4, test5, test6, test7]):
        print("✓ TEST 2 PASSED: Context maintained when filling 'CHINA'")
    else:
        print("✗ TEST 2 FAILED")
    print()
    return all([test1, test2, test3, test4, test5, test6, test7])


def test_other_conversational_responses():
    """Test that various conversational responses are rejected"""
    print("=" * 70)
    print("TEST 3: Other Conversational Responses Rejected")
    print("=" * 70)
    print()

    sm = SlotManager(redis_manager=None)

    conversational_inputs = [
        "you suggest",
        "any",
        "all countries",
        "anywhere",
        "which is best",
        "recommend one",
        "what do you think",
        "multiple",
        "several countries"
    ]

    all_passed = True
    for conv_input in conversational_inputs:
        session_id = f"test_conv_{conv_input.replace(' ', '_')}"

        params = {
            "product": "steel",
            "country": conv_input,
            "direction": "import"
        }

        state = sm.update_slots(session_id, "search_trade_data", params)

        test = "country" not in state.slots
        status = "PASS" if test else "FAIL"
        print(f"  [{status}] '{conv_input}' rejected: {test}")

        if not test:
            all_passed = False

        sm.clear_slots(session_id)

    print()
    if all_passed:
        print("✓ TEST 3 PASSED: All conversational responses rejected")
    else:
        print("✗ TEST 3 FAILED")
    print()
    return all_passed


def test_valid_countries_still_work():
    """Ensure valid countries still work after our fixes"""
    print("=" * 70)
    print("TEST 4: Valid Countries Still Work")
    print("=" * 70)
    print()

    sm = SlotManager(redis_manager=None)

    valid_countries = [
        ("china", "China"),
        ("india", "India"),
        ("usa", "USA"),
        ("united-states", "United States"),
        ("germany", "Germany"),
        ("south-korea", "South Korea")
    ]

    all_passed = True
    for country_input, expected_label in valid_countries:
        session_id = f"test_valid_{country_input}"

        params = {
            "product": "steel",
            "country": country_input,
            "direction": "export"
        }

        state = sm.update_slots(session_id, "search_trade_data", params)
        url = sm.generate_url("search_trade_data", state.slots)

        test1 = state.slots.get("country") == country_input
        test2 = url is not None
        test3 = country_input in url.lower() if url else False

        all_tests_pass = test1 and test2 and test3
        status = "PASS" if all_tests_pass else "FAIL"
        print(f"  [{status}] {expected_label}: accepted={test1}, URL={test2}")

        if not all_tests_pass:
            all_passed = False

        sm.clear_slots(session_id)

    print()
    if all_passed:
        print("✓ TEST 4 PASSED: All valid countries work correctly")
    else:
        print("✗ TEST 4 FAILED")
    print()
    return all_passed


def run_all_tests():
    """Run all user flow tests"""
    print("\n")
    print("=" * 70)
    print("USER FLOW FIXES - COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print()

    results = []

    results.append(("You Suggest Rejection", test_you_suggest_rejection()))
    results.append(("China Slot Fill", test_china_slot_fill()))
    results.append(("Conversational Responses", test_other_conversational_responses()))
    results.append(("Valid Countries", test_valid_countries_still_work()))

    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")

    all_passed = all(result[1] for result in results)
    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print()
        print("✓ Issue 1 Fixed: 'You suggest' properly rejected")
        print("✓ Issue 2 Fixed: Context maintained for slot fills")
        print("✓ Conversational responses handled correctly")
        print("✓ Valid countries still work")
    else:
        print("⚠ SOME TESTS FAILED - Review output above")
    print("=" * 70)
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
