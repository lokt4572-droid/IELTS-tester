"""Minimal Gemini client (REST). The API key is sent in a header, never in the URL or logs."""
import logging
import time

import requests
from django.conf import settings

from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(Exception):
    """A safe provider error with transient-failure metadata."""

    def __init__(self, message, fallback_allowed=False, failure_reason=None):
        super().__init__(message)
        self.fallback_allowed = fallback_allowed
        self.failure_reason = failure_reason


def build_payload(history):
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in history
    ]
    generation_config = {"temperature": 0.6, "maxOutputTokens": 2048}
    thinking_level = settings.GEMINI_THINKING_LEVEL
    thinking_budget = settings.GEMINI_THINKING_BUDGET
    if thinking_level:
        generation_config["thinkingConfig"] = {
            "thinkingLevel": thinking_level,
        }
    elif thinking_budget is not None:
        generation_config["thinkingConfig"] = {
            "thinkingBudget": thinking_budget,
        }
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": generation_config,
    }


def extract_text(data):
    for cand in data.get("candidates") or []:
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        if text.strip():
            return text.strip()
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise GeminiError("The AI declined this request. Try rephrasing your question.")
    raise GeminiError("The AI returned an empty answer. Please try again.")


def generate_reply(history, api_key=None, model=None, timeout=None):
    from django.conf import settings

    if api_key is None or model is None:
        api_key = settings.GEMINI_API_KEY if api_key is None else api_key
        model = settings.GEMINI_MODEL if model is None else model
    if timeout is None:
        timeout = settings.GEMINI_TIMEOUT_SECONDS
    if not api_key:
        raise GeminiError("The AI tutor is not configured yet.")
    payload = build_payload(history)
    retries = max(0, settings.GEMINI_503_RETRIES)
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                API_URL.format(model=model),
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
        except requests.Timeout:
            raise GeminiError(
                "The AI took too long to answer. Please try again.",
                fallback_allowed=True,
                failure_reason="timeout",
            )
        except requests.RequestException as exc:
            logger.warning("Gemini network request failed (%s)", type(exc).__name__)
            raise GeminiError(
                "Could not reach the AI service. Please try again.",
                fallback_allowed=True,
                failure_reason=type(exc).__name__,
            ) from exc
        if resp.status_code != 503 or attempt >= retries:
            break
        time.sleep(attempt + 1)

    if resp.status_code == 429:
        raise GeminiError(
            "The AI service is busy or its quota is used up. Try again in a minute.",
            fallback_allowed=True,
            failure_reason="HTTP 429",
        )
    if resp.status_code in (400, 401, 403, 404):
        logger.error("Gemini rejected the request with HTTP status %s", resp.status_code)
        raise GeminiError("The AI service rejected the request. Check the API key and model name.")
    if resp.status_code >= 400:
        logger.error("Gemini returned HTTP status %s", resp.status_code)
        raise GeminiError(
            "The AI service had a problem. Please try again.",
            fallback_allowed=resp.status_code >= 500,
            failure_reason=f"HTTP {resp.status_code}",
        )
    try:
        data = resp.json()
    except ValueError:
        raise GeminiError("The AI returned an unreadable answer. Please try again.")
    return extract_text(data)
