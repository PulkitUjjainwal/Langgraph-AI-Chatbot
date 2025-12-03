"""
Performance Benchmark Tool

Tests response times with different configurations to help optimize your chatbot.
"""

import time
import requests
import json
from statistics import mean, median

def benchmark_current_setup(num_requests=5):
    """Benchmark current chatbot setup"""

    print("=" * 70)
    print("CHATBOT PERFORMANCE BENCHMARK")
    print("=" * 70)

    api_url = "http://localhost:8000/chat"
    test_queries = [
        "What is Export Genius?",
        "Tell me about trade data coverage",
        "What countries are covered?",
        "How can I access the API?",
        "What is the pricing model?"
    ]

    times = []
    successful = 0
    failed = 0

    print(f"\nRunning {num_requests} test requests...")
    print("-" * 70)

    for i in range(num_requests):
        query = test_queries[i % len(test_queries)]

        print(f"\n[Request {i+1}/{num_requests}] Query: \"{query[:50]}...\"")

        try:
            start_time = time.time()

            response = requests.post(
                api_url,
                json={
                    "message": query,
                    "session_id": f"benchmark_user_{i}"
                },
                timeout=30
            )

            elapsed = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                processing_time = data.get("processing_time", elapsed)

                times.append(elapsed)
                successful += 1

                print(f"   Status: [OK]")
                print(f"   Total Time: {elapsed:.2f}s")
                print(f"   Server Processing: {processing_time:.2f}s")
                print(f"   Response Length: {len(data.get('response', ''))} chars")
            else:
                failed += 1
                print(f"   Status: [FAILED] HTTP {response.status_code}")

        except requests.Timeout:
            failed += 1
            print(f"   Status: [TIMEOUT] Request took > 30s")

        except Exception as e:
            failed += 1
            print(f"   Status: [ERROR] {str(e)}")

    # Statistics
    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)

    if times:
        print(f"\nSuccess Rate: {successful}/{num_requests} ({successful/num_requests*100:.1f}%)")
        print(f"Failed: {failed}")

        print(f"\n[TIMING STATISTICS]")
        print(f"   Average: {mean(times):.2f}s")
        print(f"   Median:  {median(times):.2f}s")
        print(f"   Min:     {min(times):.2f}s")
        print(f"   Max:     {max(times):.2f}s")

        print(f"\n[PERFORMANCE ASSESSMENT]")
        avg = mean(times)

        if avg < 1.0:
            rating = "EXCELLENT"
            emoji = "⚡"
            comment = "Sub-second responses - production ready!"
        elif avg < 2.0:
            rating = "VERY GOOD"
            emoji = "✅"
            comment = "Fast responses - good for production"
        elif avg < 3.0:
            rating = "GOOD"
            emoji = "👍"
            comment = "Acceptable - consider optimizing"
        elif avg < 5.0:
            rating = "FAIR"
            emoji = "⚠️"
            comment = "Slow - optimization recommended"
        else:
            rating = "POOR"
            emoji = "🔴"
            comment = "Too slow - optimization required!"

        print(f"   Rating: {emoji} {rating}")
        print(f"   Comment: {comment}")

        print(f"\n[RECOMMENDATIONS]")
        if avg > 3.0:
            print("   🔧 Switch to faster LLM model (e.g., deepseek-r1:14b)")
            print("   🔧 Reduce NUM_CTX to 2048")
            print("   🔧 Reduce NUM_PREDICT to 400")
            print("   🔧 Implement response caching")
        elif avg > 2.0:
            print("   🔧 Consider lighter model for faster responses")
            print("   🔧 Add response caching for common queries")
        else:
            print("   ✨ Performance is good! Consider:")
            print("   📊 Add monitoring to track degradation")
            print("   💾 Implement response caching for instant repeats")

    else:
        print("\n[ERROR] No successful requests completed!")
        print("Check that:")
        print("  - Server is running (http://localhost:8000)")
        print("  - Redis is running")
        print("  - Ollama is running with correct model")

    print("\n" + "=" * 70)

    return {
        "avg_time": mean(times) if times else None,
        "median_time": median(times) if times else None,
        "success_rate": successful / num_requests if num_requests > 0 else 0,
        "times": times
    }

def compare_configurations():
    """Helper to test different configurations"""

    print("\n" + "=" * 70)
    print("CONFIGURATION COMPARISON GUIDE")
    print("=" * 70)

    print("""
To test different configurations:

1. Edit fastapi_chatbot.py and change:

   # Current (slow):
   LLM_MODEL = "deepseek-v3.1:671b-cloud"

   # To faster model:
   LLM_MODEL = "deepseek-r1:14b"  # or "llama3.1:8b"

2. Restart the server:
   Ctrl+C (stop server)
   uvicorn fastapi_chatbot:app --reload

3. Run this benchmark again:
   python benchmark_performance.py

4. Compare results!

Expected improvements:
- deepseek-r1:14b:  3-4x faster (5s → 1.5s)
- llama3.1:8b:      6-8x faster (5s → 0.7s)
- gpt-4o-mini:      10x faster (5s → 0.5s, requires API key)
    """)

if __name__ == "__main__":
    import sys

    # Check server is accessible
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print("[OK] Server is running")
        else:
            print(f"[WARNING] Server returned status {response.status_code}")
    except:
        print("[ERROR] Cannot connect to server at http://localhost:8000")
        print("Please start the server first:")
        print("  uvicorn fastapi_chatbot:app --reload")
        sys.exit(1)

    # Run benchmark
    num_requests = 5
    if len(sys.argv) > 1:
        try:
            num_requests = int(sys.argv[1])
        except:
            print(f"Usage: python benchmark_performance.py [num_requests]")
            print(f"Using default: {num_requests} requests")

    results = benchmark_current_setup(num_requests)

    # Show comparison guide
    if results.get("avg_time") and results["avg_time"] > 2.0:
        compare_configurations()
