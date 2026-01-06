"""
Test Market Inside API directly to diagnose 403 errors

This script tests the Market Inside API with the exact same headers
used by unified_api_client.py to identify the root cause of 403 errors.
"""

import asyncio
import aiohttp
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = "https://api-dp.marketinsidedata.com/api/v1/users"
BEARER_TOKEN = os.getenv("MARKETINSIDE_BEARER_TOKEN", "")
DOMAIN = "marketinsidedata.com"

def get_headers():
    """Get request headers (same as unified_api_client.py)"""
    return {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9',
        'authorization': f'Bearer {BEARER_TOKEN}',
        'content-type': 'application/json',
        'origin': f'https://www.{DOMAIN}',
        'referer': f'https://www.{DOMAIN}/',
        'priority': 'u=1, i',
        'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }


async def test_endpoint(endpoint_name, endpoint_path, payload):
    """Test a single API endpoint"""
    url = f"{API_BASE_URL}{endpoint_path}"

    print(f"\n{'='*80}")
    print(f"Testing: {endpoint_name}")
    print(f"URL: {url}")
    print(f"Payload: {payload}")
    print(f"Bearer Token: {BEARER_TOKEN[:20]}...{BEARER_TOKEN[-20:]}")
    print(f"{'='*80}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=get_headers(),
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:

                status = response.status
                content_type = response.headers.get('content-type', 'unknown')

                print(f"Status: {status}")
                print(f"Content-Type: {content_type}")

                # Try to get response body
                if 'json' in content_type:
                    data = await response.json()
                    print(f"Response (JSON): {data}")
                else:
                    text = await response.text()
                    print(f"Response (Text, first 500 chars): {text[:500]}")

                if status == 200:
                    print("[SUCCESS]")
                else:
                    print(f"[FAILED] Status {status}")

                return status == 200

    except Exception as e:
        print(f"[EXCEPTION] {e}")
        return False


async def main():
    """Run all tests"""
    print(f"\n{'#'*80}")
    print("Market Inside API Diagnostic Test")
    print(f"{'#'*80}\n")

    # Test 1: Company endpoint (simpler, should work)
    # This requires a real company code - using a test one
    await test_endpoint(
        "Company Overview",
        "/company-overview",
        {
            "company_code": "test123"  # We'll see what error we get
        }
    )

    # Test 2: Search data endpoint (the one that's failing)
    await test_endpoint(
        "Search Data - Product",
        "/search-data-product",
        {
            "data_type": "detailed_imports",
            "list_type": "importer_exporter",
            "from": "2024-01-01",
            "to": "2024-12-31",
            "country": "India",
            "product": "copper"
        }
    )

    # Test 3: Search data - Suppliers (also failing)
    await test_endpoint(
        "Search Data - Suppliers",
        "/search-data-suppliers",
        {
            "data_type": "detailed_imports",
            "list_type": "buyer_supplier",
            "from": "2024-01-01",
            "to": "2024-12-31",
            "country": "India",
            "product": "copper"
        }
    )

    print(f"\n{'#'*80}")
    print("Test Complete")
    print(f"{'#'*80}\n")


if __name__ == "__main__":
    asyncio.run(main())
