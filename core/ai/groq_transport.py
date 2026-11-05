"""Shared Groq chat-completions HTTP transport."""

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

API_URL = "https://api.groq.com/openai/v1/chat/completions"
RETRY_DELAYS = (1, 3)
REASONING_EFFORT_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
}

logger = logging.getLogger(__name__)


class GroqTransportError(Exception):
    """A network failure safe to translate into a provider-specific error."""


def _retry_after_seconds(response):
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def chat_completion(
    messages,
    api_key,
    model,
    timeout,
    max_tokens,
    temperature,
    response_format=None,
    reasoning_effort=None,
    include_reasoning=None,
    reasoning_effort_setting_name="GROQ_REASONING_EFFORT",
    retries=True,
):
    request_data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format is not None:
        request_data["response_format"] = response_format
    if reasoning_effort:
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError(
                f"{reasoning_effort_setting_name} must be low, medium, or high."
            )
        if model in REASONING_EFFORT_MODELS:
            request_data["reasoning_effort"] = reasoning_effort
    if include_reasoning is not None:
        request_data["include_reasoning"] = include_reasoning

    attempts = len(RETRY_DELAYS) + 1 if retries else 1
    for attempt in range(attempts):
        try:
            response = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_data,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt < attempts - 1:
                time.sleep(RETRY_DELAYS[attempt])
                continue
            logger.error("Groq transport failed after retries (%s)", type(exc).__name__)
            raise GroqTransportError(
                "Could not reach the Groq service. Please try again."
            ) from exc

        if (response.status_code == 429 or response.status_code >= 500) and attempt < attempts - 1:
            retry_after = _retry_after_seconds(response)
            delay = max(RETRY_DELAYS[attempt], retry_after or 0)
            time.sleep(delay)
            continue
        return response

    raise GroqTransportError("Could not reach the Groq service. Please try again.")
