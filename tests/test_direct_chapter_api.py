"""
Test calling the chapter API directly with different payloads
"""
import asyncio
import httpx
import json

async def test_chapter_api():
    base_url = "https://api-dp.marketinsidedata.com/api/v1/users"
    endpoint = "/chapter-details"

    # Auth token from .env
    bearer_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjMwNzk0OWNiLWZmODItNGVkOS1hNzZhLWMxOGRmOThiZDZkYyIsImlhdCI6MTcwNDU0OTU4MH0.sMR6ZZ52KNkiXG8V-Y6JxjkscCOOEDY7DPEFc5nMU88"

    headers = {
        'accept': 'application/json, text/plain, */*',
        'authorization': f'Bearer {bearer_token}',
        'content-type': 'application/json',
        'origin': 'https://www.marketinsidedata.com',
        'referer': 'https://www.marketinsidedata.com/'
    }

    # Test different payload variations
    payloads = [
        {
            "name": "With country_code='argentina' (lowercase)",
            "payload": {
                "data_type": "custom_data",
                "direction": "import",
                "country_code": "argentina",
                "chapter": "49"
            }
        },
        {
            "name": "With country_code='Argentina' (capitalized)",
            "payload": {
                "data_type": "custom_data",
                "direction": "import",
                "country_code": "Argentina",
                "chapter": "49"
            }
        },
        {
            "name": "With country_code='AR' (ISO code)",
            "payload": {
                "data_type": "custom_data",
                "direction": "import",
                "country_code": "AR",
                "chapter": "49"
            }
        },
        {
            "name": "With country_code='ar' (ISO lowercase)",
            "payload": {
                "data_type": "custom_data",
                "direction": "import",
                "country_code": "ar",
                "chapter": "49"
            }
        }
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        for test in payloads:
            print("=" * 80)
            print(f"TEST: {test['name']}")
            print("=" * 80)
            print(f"Payload: {json.dumps(test['payload'], indent=2)}")
            print()

            try:
                response = await client.post(
                    base_url + endpoint,
                    json=test['payload'],
                    headers=headers
                )

                print(f"Status: {response.status_code}")

                if response.status_code == 200:
                    data = response.json()

                    # Check key fields
                    country = data.get("country", "NOT FOUND")
                    total_value = data.get("total_value", 0)
                    total_shipments = data.get("total_shipments", 0)
                    chapter_table_len = len(data.get("chapter_table", []))

                    print(f"Country: '{country}'")
                    print(f"Total Value: {total_value:,}")
                    print(f"Total Shipments: {total_shipments:,}")
                    print(f"Chapter Table Items: {chapter_table_len}")

                    if total_value > 0:
                        print("\n✓ SUCCESS - API returned data!")
                        print("\nSample chapter table item:")
                        if data.get("chapter_table"):
                            print(json.dumps(data["chapter_table"][0], indent=2))
                        break  # Found working payload
                    else:
                        print("\n✗ FAILED - No data returned")
                else:
                    print(f"Error: {response.text[:200]}")

            except Exception as e:
                print(f"Exception: {e}")

            print()

if __name__ == "__main__":
    asyncio.run(test_chapter_api())
