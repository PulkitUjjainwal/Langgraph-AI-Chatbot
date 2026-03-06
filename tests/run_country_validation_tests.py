"""
Direct test runner for country validation (no pytest dependency)
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from chatbot.services.slot_manager import SlotManager, SlotConfig


def run_tests():
    """Run all country validation tests"""

    print("=" * 70)
    print("COUNTRY VALIDATION TEST SUITE")
    print("=" * 70)
    print()

    passed = 0
    failed = 0

    # Test 1: Valid single-word countries
    print("TEST 1: Valid single-word countries")
    sm = SlotManager(redis_manager=None)
    tests = [
        ("india", True),
        ("china", True),
        ("usa", True),
        ("france", True),
    ]

    for country, expected in tests:
        result = sm.is_valid_country(country)
        status = "[PASS]" if result == expected else "[FAIL]"
        print(f"  {status}: is_valid_country('{country}') = {result}")
        if result == expected:
            passed += 1
        else:
            failed += 1
    print()

    # Test 2: Valid multi-word countries
    print("TEST 2: Valid multi-word countries")
    tests = [
        ("united states", True),
        ("united kingdom", True),
        ("south korea", True),
        ("south africa", True),
    ]

    for country, expected in tests:
        result = sm.is_valid_country(country)
        status = "[PASS]" if result == expected else "[FAIL]"
        print(f"  {status}: is_valid_country('{country}') = {result}")
        if result == expected:
            passed += 1
        else:
            failed += 1
    print()

    # Test 3: Invalid countries
    print("TEST 3: Invalid countries (should reject)")
    tests = [
        ("atlantis", False),
        ("narnia", False),
        ("wakanda", False),
        ("Do-It.", False),
        ("All-You.", False),
    ]

    for country, expected in tests:
        result = sm.is_valid_country(country)
        status = "[PASS]" if result == expected else "[FAIL]"
        print(f"  {status}: is_valid_country('{country}') = {result}")
        if result == expected:
            passed += 1
        else:
            failed += 1
    print()

    # Test 4: Slot update with valid countries
    print("TEST 4: Slot update with valid countries")
    session_id = "test_valid"
    params = {
        "origin_country": "belgium",
        "destination_country": "france",
        "direction": "export"
    }

    state = sm.update_slots(session_id, "country_to_country", params)

    test_1 = state.slots.get("origin_country") == "belgium"
    test_2 = state.slots.get("destination_country") == "france"
    test_3 = len(state.missing_slots) == 0

    print(f"  {'✓ PASS' if test_1 else '✗ FAIL'}: origin_country stored = {state.slots.get('origin_country')}")
    print(f"  {'✓ PASS' if test_2 else '✗ FAIL'}: destination_country stored = {state.slots.get('destination_country')}")
    print(f"  {'✓ PASS' if test_3 else '✗ FAIL'}: no missing slots = {len(state.missing_slots) == 0}")

    if test_1:
        passed += 1
    else:
        failed += 1
    if test_2:
        passed += 1
    else:
        failed += 1
    if test_3:
        passed += 1
    else:
        failed += 1

    sm.clear_slots(session_id)
    print()

    # Test 5: Slot update with invalid origin
    print("TEST 5: Slot update with invalid origin (should reject origin)")
    session_id = "test_invalid_origin"
    params = {
        "origin_country": "atlantis",
        "destination_country": "france",
        "direction": "export"
    }

    state = sm.update_slots(session_id, "country_to_country", params)

    test_1 = "origin_country" not in state.slots
    test_2 = state.slots.get("destination_country") == "france"
    test_3 = "origin_country" in state.missing_slots

    print(f"  {'✓ PASS' if test_1 else '✗ FAIL'}: invalid origin removed = {'origin_country' not in state.slots}")
    print(f"  {'✓ PASS' if test_2 else '✗ FAIL'}: valid destination kept = {state.slots.get('destination_country')}")
    print(f"  {'✓ PASS' if test_3 else '✗ FAIL'}: origin marked missing = {'origin_country' in state.missing_slots}")

    if test_1:
        passed += 1
    else:
        failed += 1
    if test_2:
        passed += 1
    else:
        failed += 1
    if test_3:
        passed += 1
    else:
        failed += 1

    sm.clear_slots(session_id)
    print()

    # Test 6: Slot update with both invalid (ORIGINAL BUG SCENARIO)
    print("TEST 6: ORIGINAL BUG SCENARIO - Both invalid (Do-It., All-You.)")
    session_id = "test_bug"
    params = {
        "origin_country": "Do-It.",
        "destination_country": "All-You.",
        "direction": "import"
    }

    state = sm.update_slots(session_id, "country_to_country", params)

    test_1 = "origin_country" not in state.slots
    test_2 = "destination_country" not in state.slots

    print(f"  {'✓ PASS' if test_1 else '✗ FAIL'}: Do-It. rejected = {'origin_country' not in state.slots}")
    print(f"  {'✓ PASS' if test_2 else '✗ FAIL'}: All-You. rejected = {'destination_country' not in state.slots}")

    if test_1:
        passed += 1
    else:
        failed += 1
    if test_2:
        passed += 1
    else:
        failed += 1

    sm.clear_slots(session_id)
    print()

    # Test 7: URL generation with valid countries
    print("TEST 7: URL generation with valid countries")
    slots = {
        "origin_country": "belgium",
        "destination_country": "france",
        "direction": "export"
    }

    url = sm.generate_url("country_to_country", slots)

    test_1 = url is not None
    test_2 = "Belgium" in url if url else False
    test_3 = "France" in url if url else False
    test_4 = "/cntry/" in url if url else False

    print(f"  {'✓ PASS' if test_1 else '✗ FAIL'}: URL generated = {url is not None}")
    print(f"  {'✓ PASS' if test_2 else '✗ FAIL'}: Contains Belgium = {test_2}")
    print(f"  {'✓ PASS' if test_3 else '✗ FAIL'}: Contains France = {test_3}")
    print(f"  {'✓ PASS' if test_4 else '✗ FAIL'}: Contains /cntry/ = {test_4}")
    if url:
        print(f"  Generated URL: {url}")

    if test_1:
        passed += 1
    else:
        failed += 1
    if test_2:
        passed += 1
    else:
        failed += 1
    if test_3:
        passed += 1
    else:
        failed += 1
    if test_4:
        passed += 1
    else:
        failed += 1
    print()

    # Test 8: URL generation with invalid countries (ORIGINAL BUG - Should return None)
    print("TEST 8: URL generation with invalid countries (should return None)")
    slots = {
        "origin_country": "Do-It.",
        "destination_country": "All-You.",
        "direction": "import"
    }

    url = sm.generate_url("country_to_country", slots)

    test_1 = url is None
    malformed_url = "https://www.marketinsidedata.com/en/cntry/Do-It.-import-All-You."
    test_2 = url != malformed_url

    print(f"  {'✓ PASS' if test_1 else '✗ FAIL'}: URL is None = {url is None}")
    print(f"  {'✓ PASS' if test_2 else '✗ FAIL'}: Malformed URL NOT created = {url != malformed_url}")
    if url:
        print(f"  WARNING: URL was generated: {url}")

    if test_1:
        passed += 1
    else:
        failed += 1
    if test_2:
        passed += 1
    else:
        failed += 1
    print()

    # Test 9: Existing intents not affected
    print("TEST 9: Existing intents not affected (search_country_data)")
    session_id = "test_other_intent"
    params = {"country": "india", "direction": "import"}

    state = sm.update_slots(session_id, "search_country_data", params)

    test_1 = state.slots.get("country") == "india"
    test_2 = state.intent == "search_country_data"

    print(f"  {'✓ PASS' if test_1 else '✗ FAIL'}: country slot set = {state.slots.get('country')}")
    print(f"  {'✓ PASS' if test_2 else '✗ FAIL'}: intent preserved = {state.intent}")

    if test_1:
        passed += 1
    else:
        failed += 1
    if test_2:
        passed += 1
    else:
        failed += 1

    sm.clear_slots(session_id)
    print()

    # Test 10: Continent detection not affected
    print("TEST 10: Continent detection not affected")
    tests = [
        ("africa", True),
        ("asia", True),
        ("europe", True),
        ("india", False),  # country, not continent
    ]

    for continent, expected in tests:
        result = sm.is_continent(continent)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        print(f"  {status}: is_continent('{continent}') = {result}")
        if result == expected:
            passed += 1
        else:
            failed += 1
    print()

    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total: {passed + failed}")
    print(f"✓ Passed: {passed}")
    print(f"✗ Failed: {failed}")
    print()

    if failed == 0:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"⚠ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
