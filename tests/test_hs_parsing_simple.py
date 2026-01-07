"""
Simple standalone test for HS Code URL parsing (no module imports)
"""

from urllib.parse import urlparse, unquote

def parse_hs_code_url(url: str):
    """Standalone version of _parse_hs_code_url for testing"""
    # Extract the last segment from path
    parsed = urlparse(url)
    path_segments = [p for p in parsed.path.split('/') if p]

    if not path_segments:
        return {"error": "Could not parse URL path"}

    last_segment = path_segments[-1]

    # Split by hyphen: [country]-[direction]-hs-code-[code]
    parts = last_segment.split('-')

    if len(parts) < 4:
        return {"error": f"Invalid URL format: expected [country]-[direction]-hs-code-[code], got {last_segment}"}

    # Find "hs" and "code" keywords
    hs_index = -1
    for i, part in enumerate(parts):
        if part.lower() == 'hs' and i + 1 < len(parts) and parts[i + 1].lower() == 'code':
            hs_index = i
            break

    if hs_index == -1:
        return {"error": f"Could not find 'hs-code' in URL: {last_segment}"}

    # Find direction keyword before "hs-code"
    direction_index = -1
    direction = None

    for i in range(hs_index):
        if parts[i].lower() in ['import', 'export']:
            direction_index = i
            direction = parts[i].lower()
            break

    if direction_index == -1:
        return {"error": f"Could not find 'import' or 'export' in URL: {last_segment}"}

    # Everything before direction is country name
    country_parts = parts[:direction_index]

    # Everything after "code" is the HS code
    code_parts = parts[hs_index + 2:]  # Skip "hs" and "code"

    if not country_parts or not code_parts:
        return {"error": f"Missing country or HS code in URL: {last_segment}"}

    # Join parts and decode URL encoding
    country_name = unquote('-'.join(country_parts))
    hs_code = ''.join(code_parts)  # Join without separator for HS code

    # Keep country name lowercase (API expects lowercase)
    country_name = country_name.replace('-', ' ').lower()

    # Determine hierarchy level based on code length
    code_length = len(hs_code)
    if code_length == 2:
        hierarchy_level = "chapter"
    elif code_length == 4:
        hierarchy_level = "heading"
    elif code_length == 6:
        hierarchy_level = "subheading"
    elif code_length >= 8:
        hierarchy_level = "hs_code"
    else:
        return {"error": f"Invalid HS code length: {code_length} (expected 2, 4, 6, or 8+ digits)"}

    return {
        "country_name": country_name,
        "data_type": direction,
        "hs_code": hs_code,
        "hierarchy_level": hierarchy_level
    }


# Test URLs
test_cases = [
    ("https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-27", "chapter", "27", "botswana", "import"),
    ("https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-2710", "heading", "2710", "botswana", "import"),
    ("https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-271012", "subheading", "271012", "botswana", "import"),
    ("https://www.marketinsidedata.com/en/chapter/botswana-import-hs-code-27101230", "hs_code", "27101230", "botswana", "import"),
    ("https://www.marketinsidedata.com/en/chapter/south%20africa-export-hs-code-84", "chapter", "84", "south africa", "export"),
]

print("=" * 80)
print("HS CODE URL PARSING TEST (Standalone)")
print("=" * 80)
print()

all_passed = True

for url, expected_level, expected_code, expected_country, expected_direction in test_cases:
    print(f"Testing: {url}")
    print("-" * 80)

    result = parse_hs_code_url(url)

    if "error" in result:
        print(f"[FAIL] {result['error']}")
        all_passed = False
    else:
        country = result['country_name']
        direction = result['data_type']
        code = result['hs_code']
        level = result['hierarchy_level']

        print(f"  Country: '{country}' (expected: '{expected_country}')")
        print(f"  Direction: '{direction}' (expected: '{expected_direction}')")
        print(f"  HS Code: '{code}' (expected: '{expected_code}')")
        print(f"  Level: '{level}' (expected: '{expected_level}')")

        if country == expected_country and direction == expected_direction and code == expected_code and level == expected_level:
            print("  [SUCCESS] All fields match!")
            print()
            print("  API Payload would be:")
            print(f'  {{"data_type": "custom_data", "direction": "{direction}", "country_code": "{country}", "hs_code": "{code}"}}')
        else:
            print("  [FAIL] Field mismatch!")
            all_passed = False

    print()

print("=" * 80)
if all_passed:
    print("[SUCCESS] All tests passed!")
else:
    print("[FAIL] Some tests failed")
print("=" * 80)
