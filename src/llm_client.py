"""
Thin wrapper around a generative AI API (called directly via REST, no SDK
dependency needed), used by both agent.py and explain.py.

Runs on a free-tier model - no billing required. Set your API key as
AI_API_KEY before running any script that uses this module.

Two things the free tier requires handling for:
  1. Model names change fairly often as older versions are retired, so
     calls try a short list of candidate models in order and cache
     whichever one responds successfully.
  2. The free tier has a low rate limit (requests per minute). A 429
     response means "wait and retry," not "this model is broken" - so
     429s get a longer backoff and retry, separate from other errors
     which move on to the next candidate model.
"""

import os
import time
import requests

AI_API_KEY = os.environ.get("AI_API_KEY")

_CANDIDATE_MODELS = [
    os.environ.get("AI_MODEL"),  # explicit override, if set
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
]
_CANDIDATE_MODELS = [m for m in _CANDIDATE_MODELS if m]

_working_model = None  # cached once a working model is found

# Minimum gap enforced between any two calls, to stay under free-tier
# rate limits even when running many cases back to back.
_MIN_SECONDS_BETWEEN_CALLS = 4
_last_call_time = 0


def _url_for(model):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _wait_for_rate_limit():
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(_MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_time = time.time()


def call_llm(prompt, max_tokens=300, retries=1):
    """
    Sends a single-turn prompt to a working model and returns the plain
    text response. Automatically paces calls to respect free-tier rate
    limits, and retries with backoff on 429 (rate limited) responses.
    """
    global _working_model

    if not AI_API_KEY:
        raise RuntimeError(
            "AI_API_KEY is not set. Get a free key at "
            "https://aistudio.google.com/app/apikey and set it as an "
            "environment variable before running this script."
        )

    models_to_try = [_working_model] if _working_model else _CANDIDATE_MODELS
    last_error = None

    for model in models_to_try:
        attempt = 0
        while attempt <= retries:
            _wait_for_rate_limit()
            try:
                resp = requests.post(
                    _url_for(model),
                    params={"key": AI_API_KEY},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"maxOutputTokens": max_tokens},
                    },
                    timeout=60,
                )

                if resp.status_code == 429:
                    # Rate limited - wait longer and retry the SAME model,
                    # this isn't a reason to move to a different one.
                    wait_time = 20 * (attempt + 1)
                    print(f"  Rate limited, waiting {wait_time}s before retrying...", flush=True)
                    time.sleep(wait_time)
                    attempt += 1
                    continue

                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                _working_model = model
                return text

            except (requests.exceptions.RequestException, KeyError, IndexError) as e:
                last_error = e
                break  # move to the next candidate model

    raise RuntimeError(
        f"All candidate models failed (tried {models_to_try}). "
        f"Last error: {last_error}. Check https://ai.google.dev/gemini-api/docs/models "
        f"for currently available model names and set AI_MODEL to override."
    )
