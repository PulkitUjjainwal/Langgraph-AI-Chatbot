"""
Test script for HS Code URL parsing and hierarchy detection

Tests all 4 hierarchy levels:
1. Chapter (2 digits)
2. Heading (4 digits)
3. Subheading (6 digits)
4. HS Code (8+ digits)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chatbot.integrations.apis.unified_api_client import UnifiedAPIClient, PageType

# Test URLs from user
test_urls = [
    {
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-27",
        "expected_level": "chapter",
        "expected_code": "27",
        "expected_country": "botswana",
        "expected_direction": "import"
    },
    {
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-2710",
        "expected_level": "heading",
        "expected_code": "2710",
        "expected_country": "botswana",
        "expected_direction": "import"
    },
    {
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-271012",
        "expected_level": "subheading",
        "expected_code": "271012",
        "expected_country": "botswana",
        "expected_direction": "import"
    },
    {
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-27101230",
        "expected_level": "hs_code",
        "expected_code": "27101230",
        "expected_country": "botswana",
        "expected_direction": "import"
    },
]

# Additional test cases with different countries and directions
additional_tests = [
    {
        "url": "https://www.marketinsidedata.com/en/chapter/south%20africa-export-hs-code-84",
        "expected_level": "chapter",
        "expected_code": "84",
        "expected_country": "south africa",
        "expected_direction": "export"
    },
    {
        "url": "https://www.marketinsidedata.com/en/chapter/united-states-import-hs-code-8471",
        "expected_level": "heading",
        "expected_code": "8471",
        "expected_country": "united states",
        "expected_direction": "import"
    },
]

print("=" * 80)
print("HS CODE URL PARSING TEST")
print("=" * 80)
print()

all_passed = True

for i, test_case in enumerate(test_urls + additional_tests, 1):
    url = test_case["url"]
    print(f"Test {i}: {test_case['expected_level'].upper()}")
    print(f"URL: {url}")
    print("-" * 80)

    # Test page type detection
    page_type = UnifiedAPIClient.detect_page_type(url)
    print(f"Page Type Detection: {page_type.value}")

    if page_type != PageType.HS_CODE:
        print("[FAIL] Page type should be HS_CODE")
        all_passed = False
        print()
        continue

    # Test URL parsing
    params = UnifiedAPIClient._parse_hs_code_url(url)

    if "error" in params:
        print(f"[FAIL] {params['error']}")
        all_passed = False
        print()
        continue

    # Validate parsed parameters
    country_name = params.get("country_name")
    data_type = params.get("data_type")
    hs_code = params.get("hs_code")
    hierarchy_level = params.get("hierarchy_level")

    print(f"Parsed Country: '{country_name}'")
    print(f"Parsed Direction: '{data_type}'")
    print(f"Parsed HS Code: '{hs_code}'")
    print(f"Detected Level: '{hierarchy_level}'")
    print()

    # Validate against expected values
    errors = []

    if country_name != test_case["expected_country"]:
        errors.append(f"  Country mismatch: expected '{test_case['expected_country']}', got '{country_name}'")

    if data_type != test_case["expected_direction"]:
        errors.append(f"  Direction mismatch: expected '{test_case['expected_direction']}', got '{data_type}'")

    if hs_code != test_case["expected_code"]:
        errors.append(f"  HS Code mismatch: expected '{test_case['expected_code']}', got '{hs_code}'")

    if hierarchy_level != test_case["expected_level"]:
        errors.append(f"  Level mismatch: expected '{test_case['expected_level']}', got '{hierarchy_level}'")

    if errors:
        print("[FAIL] Validation errors:")
        for error in errors:
            print(error)
        all_passed = False
    else:
        print("[SUCCESS] All validations passed!")

        # Show what the API payload would look like
        print()
        print("API Request Payload:")
        print("  {")
        print(f'    "data_type": "custom_data",')
        print(f'    "direction": "{data_type}",')
        print(f'    "country_code": "{country_name}",')
        print(f'    "hs_code": "{hs_code}"')
        print("  }")

    print()
    print("=" * 80)
    print()

# Summary
print()
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)

if all_passed:
    print("[SUCCESS] All tests passed!")
    print()
    print("The HS Code URL parsing implementation is working correctly:")
    print("  - Page type detection works for /chapter/ URLs")
    print("  - URL parsing extracts country, direction, and HS code correctly")
    print("  - Hierarchy level detection works based on code length")
    print("  - Country names are lowercase (as expected by API)")
    print("  - Multi-word countries with URL encoding are handled correctly")
else:
    print("[FAIL] Some tests failed. Please review the errors above.")

print("=" * 80)
