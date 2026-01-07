"""
Simple test for URL parsing (no imports needed)
"""

from urllib.parse import urlparse, unquote

def parse_c2c_url(url: str):
    """Standalone version of _parse_c2c_url for testing"""
    # Extract the last segment from path
    parsed = urlparse(url)
    path_segments = [p for p in parsed.path.split('/') if p]

    if not path_segments:
        return {"error": "Could not parse URL path"}

    last_segment = path_segments[-1]

    # Split by hyphen: [origin]-[direction]-[destination]
    parts = last_segment.split('-')

    if len(parts) < 3:
        return {"error": f"Invalid URL format: expected [origin]-[direction]-[destination], got {last_segment}"}

    # Find the direction keyword (import or export)
    direction_index = -1
    direction = None

    for i, part in enumerate(parts):
        if part.lower() in ['import', 'export']:
            direction_index = i
            direction = part.lower()
            break

    if direction_index == -1:
        return {"error": f"Could not find 'import' or 'export' in URL: {last_segment}"}

    # Everything before direction is origin country
    origin_parts = parts[:direction_index]
    # Everything after direction is destination country
    destination_parts = parts[direction_index + 1:]

    if not origin_parts or not destination_parts:
        return {"error": f"Missing origin or destination country in URL: {last_segment}"}

    # Join parts with hyphens and decode URL encoding
    origin_country = unquote('-'.join(origin_parts))
    destination_country = unquote('-'.join(destination_parts))

    # Keep country names lowercase and replace hyphens with spaces
    # API expects lowercase country names (e.g., "south africa", "argentina")
    origin_country = origin_country.replace('-', ' ').lower()
    destination_country = destination_country.replace('-', ' ').lower()

    return {
        "origin_country": origin_country,
        "destination_country": destination_country,
        "data_type": direction
    }


# Test with the failing URL
test_url = "https://www.marketinsidedata.com/en/cntry/botswana-import-south%20africa"

print("Testing URL parsing fix:")
print("="*80)
print(f"URL: {test_url}")
print()

result = parse_c2c_url(test_url)

if "error" in result:
    print(f"[ERROR] {result['error']}")
else:
    print("[SUCCESS] Successfully parsed!")
    print(f"  Origin Country: '{result['origin_country']}'")
    print(f"  Destination Country: '{result['destination_country']}'")
    print(f"  Data Type: '{result['data_type']}'")
    print()
    print("Expected API payload:")
    print(f"  {{")
    print(f"    \"data_type\": \"{result['data_type']}\",")
    print(f"    \"country_name\": \"{result['origin_country']}\",")
    if result['data_type'] == 'import':
        print(f"    \"origin_country\": \"{result['destination_country']}\"")
    else:
        print(f"    \"destination_country\": \"{result['destination_country']}\"")
    print(f"  }}")
    print()
    print("[SUCCESS] Country names are now in lowercase (as expected by API)")

print("\n" + "="*80)
print("Testing additional URLs:")
print("="*80)

additional_urls = [
    "https://www.marketinsidedata.com/en/cntry/Belgium-export-France",
    "https://www.marketinsidedata.com/en/cntry/United%20States-import-India",
    "https://www.marketinsidedata.com/en/cntry/argentina-import-brazil",
]

for test_url in additional_urls:
    result = parse_c2c_url(test_url)
    status = "[OK]" if "error" not in result else "[FAIL]"
    print(f"\n{status} {test_url}")
    if "error" not in result:
        print(f"   {result['origin_country']} {result['data_type']}s from/to {result['destination_country']}")
