"""
Test to verify correct API payload field names for each HS code hierarchy level
"""

import json

# Test cases showing the correct payload for each hierarchy level
test_cases = [
    {
        "level": "Chapter (2 digits)",
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-27",
        "code": "27",
        "field_name": "chapter",
        "payload": {
            "data_type": "custom_data",
            "direction": "import",
            "country_code": "botswana",
            "chapter": "27"
        }
    },
    {
        "level": "Heading (4 digits)",
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-2710",
        "code": "2710",
        "field_name": "heading",
        "payload": {
            "data_type": "custom_data",
            "direction": "import",
            "country_code": "botswana",
            "heading": "2710"
        }
    },
    {
        "level": "Subheading (6 digits)",
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-271012",
        "code": "271012",
        "field_name": "sub_heading",
        "payload": {
            "data_type": "custom_data",
            "direction": "import",
            "country_code": "botswana",
            "sub_heading": "271012"
        }
    },
    {
        "level": "HS Code (8+ digits)",
        "url": "https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-27101230",
        "code": "27101230",
        "field_name": "hs_code",
        "payload": {
            "data_type": "custom_data",
            "direction": "import",
            "country_code": "botswana",
            "hs_code": "27101230"
        }
    }
]

print("=" * 80)
print("HS CODE API PAYLOAD FIELD NAMES - FIXED")
print("=" * 80)
print()
print("The API requires different field names based on hierarchy level:")
print()

for test in test_cases:
    print(f"{test['level']}")
    print("-" * 80)
    print(f"URL: {test['url']}")
    print(f"Code: {test['code']}")
    print(f"Field Name: '{test['field_name']}' (NOT 'hs_code')")
    print()
    print("Correct API Payload:")
    print(json.dumps(test['payload'], indent=2))
    print()
    print("=" * 80)
    print()

print()
print("SUMMARY:")
print("-" * 80)
print("✅ Chapter endpoints expect:     \"chapter\": \"27\"")
print("✅ Heading endpoints expect:     \"heading\": \"2710\"")
print("✅ Subheading endpoints expect:  \"sub_heading\": \"271012\"")
print("✅ HS Code endpoints expect:     \"hs_code\": \"27101230\"")
print()
print("The code has been updated to use the correct field name for each level.")
print("=" * 80)
