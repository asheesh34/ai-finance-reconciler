"""
Thin wrapper around a generative AI API (called directly via REST, no SDK
dependency needed), used by both agent.py and explain.py.

Runs on a free-tier model - no billing required. Set your API key as
AI_API_KEY before running any script that uses this module.

Model names on the free tier change fairly often as providers retire
older versions. To keep this working without manual updates, calls try
a short list of candidate models in order and use the first one that
responds successfully, rather than hardcoding a single name that could
be retired at any time. Override with the AI_MODEL environment
variable to force a specific model.

Kept as a single shared module so the underlying provider/model can be
swapped later by editing one file instead of two.
"""

import os
import requests

AI_API_KEY = os.environ.get("AI_API_KEY")

# Tried in order; the first model that responds successfully is used
# for the rest of the run. Includes a couple of generations back as a
# safety net in case the newest alias isn't available on a given key.
_CANDIDATE_MODELS = [
    os.environ.get("AI_MODEL"),  # explicit override, if set
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
]
_CANDIDATE_MODELS = [m for m in _CANDIDATE_MODELS if m]  # drop the None if AI_MODEL unset

_working_model = None  # cached once a working model is found, so we don't re-probe every call


def _url_for(model):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def call_llm(prompt, max_tokens=300, retries=1):
    """
    Sends a single-turn prompt to a working model and returns the plain
    text response. Raises a clear error if the API key is missing or
    every candidate model fails after retries.
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
        for attempt in range(retries + 1):
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
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                _working_model = model  # remember this one worked, skip probing next time
                return text
            except (requests.exceptions.RequestException, KeyError, IndexError) as e:
                last_error = e
                continue

    raise RuntimeError(
        f"All candidate models failed (tried {models_to_try}). "
        f"Last error: {last_error}. Check https://ai.google.dev/gemini-api/docs/models "
        f"for currently available model names and set AI_MODEL to override."
    )
