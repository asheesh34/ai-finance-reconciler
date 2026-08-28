"""
Thin wrapper around Google's Gemini API (called directly via REST, no SDK
dependency needed), used by both agent.py and explain.py.

Uses Gemini's free tier - no billing required. Get a free API key at
https://aistudio.google.com/app/apikey and set it as GEMINI_API_KEY.

Kept as a single shared module so the AI provider can be swapped later
(e.g. back to Claude, or to another model) by editing one file instead
of two.
"""

import os
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def call_llm(prompt, max_tokens=300):
    """
    Sends a single-turn prompt to Gemini and returns the plain text response.
    Raises a clear error if the API key is missing or the call fails.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a free key at "
            "https://aistudio.google.com/app/apikey and set it as an "
            "environment variable before running this script."
        )

    resp = requests.post(
        API_URL,
        params={"key": GEMINI_API_KEY},
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
        raise RuntimeError(f"Unexpected Gemini response shape: {data}")
