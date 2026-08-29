"""
Quick sanity check - makes exactly one API call and prints the result.
Run this first if the full evaluation seems stuck, to quickly tell
whether it's a real connectivity/firewall issue or just normal latency.

Usage:
    export AI_API_KEY=your_key_here
    python3 tests/test_connection.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_client import call_llm

if __name__ == "__main__":
    print("Sending one test request... (this should take a few seconds, not minutes)")
    try:
        result = call_llm("Reply with exactly one word: hello", max_tokens=10)
        print(f"SUCCESS. Response: {result}")
    except Exception as e:
        print(f"FAILED: {e}")
