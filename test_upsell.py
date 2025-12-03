"""Test: Chatbot should UPSELL Export Genius"""
import requests
import time

API_URL = "http://localhost:8000/chat"

def test_export_genius_upsell():
    """Test that chatbot actively promotes Export Genius"""

    print("\n" + "="*70)
    print("UPSELL TEST: Ask about Export Genius")
    print("="*70)

    # Wait for server to reload
    print("\nWaiting 3 seconds for server reload...")
    time.sleep(3)

    payload = {
        "message": "Tell me about Export Genius. What can it do?",
        "session_id": "test_upsell_user"
    }

    print(f"\nSending request...")
    print(f"  Query: {payload['message']}")

    try:
        response = requests.post(API_URL, json=payload, timeout=30)

        if response.status_code == 200:
            data = response.json()
            answer = data['response']

            print(f"\n[RESPONSE RECEIVED]")
            print(f"  Status: {response.status_code}")
            print(f"  Processing time: {data.get('processing_time', 0):.2f}s")
            print(f"\n{answer}")

            # Check if response is positive and promotional
            answer_lower = answer.lower()

            success_indicators = [
                ("mentions countries", "190" in answer or "countries" in answer_lower),
                ("mentions data coverage", "trade data" in answer_lower or "shipment" in answer_lower),
                ("mentions contacts", "contacts" in answer_lower or "10m" in answer_lower),
                ("mentions API", "api" in answer_lower),
                ("is enthusiastic", "!" in answer or "can" in answer_lower)
            ]

            failure_indicators = [
                ("says no information", "don't have" in answer_lower or "no information" in answer_lower),
                ("is too cautious", "i'm not sure" in answer_lower or "i cannot" in answer_lower)
            ]

            print(f"\n{'='*70}")
            print("ANALYSIS:")
            print(f"{'='*70}")

            # Check success indicators
            passed = 0
            for indicator, check in success_indicators:
                status = "[OK]" if check else "[MISSING]"
                print(f"{status} {indicator}")
                if check:
                    passed += 1

            # Check failure indicators
            for indicator, check in failure_indicators:
                if check:
                    print(f"[FAIL] {indicator}")
                    passed = 0
                    break

            print(f"\n{'='*70}")
            if passed >= 3 and not any(check for _, check in failure_indicators):
                print("[SUCCESS] Chatbot is UPSELLING Export Genius!")
                print(f"{'='*70}")
                return True
            else:
                print("[FAILED] Chatbot is NOT properly upselling")
                print(f"{'='*70}")
                return False

        else:
            print(f"\n[ERROR] HTTP {response.status_code}")
            print(f"  {response.text}")
            return False

    except Exception as e:
        print(f"\n[ERROR] Request failed: {e}")
        return False


if __name__ == "__main__":
    success = test_export_genius_upsell()
    exit(0 if success else 1)
