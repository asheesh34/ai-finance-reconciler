"""
Thin wrapper around a generative AI API (called directly via REST, no SDK
dependency needed), used by both agent.py and explain.py.

Runs on a free-tier model - no billing required. Set your API key as
AI_API_KEY before running any script that uses this module.

Kept as a single shared module so the underlying provider/model can be
swapped later by editing one file instead of two.
"""

import os
import requests

AI_API_KEY = os.environ.get("AI_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL", "gemini-2.0-flash")

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent"


def call_llm(prompt, max_tokens=300):
    """
    Sends a single-turn prompt to the configured model and returns the
    plain text response. Raises a clear error if the API key is missing
    or the call fails.
    """
    if not AI_API_KEY:
        raise RuntimeError(
            "AI_API_KEY is not set. Get a free key at "
            "https://aistudio.google.com/app/apikey and set it as an "
            "environment variable before running this script."
        )

    resp = requests.post(
        API_URL,
        params={"key": AI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected AI API response shape: {data}")
