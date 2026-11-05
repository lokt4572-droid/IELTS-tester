"""Groq chat client using the shared authenticated/retrying transport."""

import logging

from django.conf import settings

from core.ai.groq_transport import (
    API_URL,
    REASONING_EFFORT_MODELS,
    GroqTransportError,
    chat_completion,
)
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GroqChatError(Exception):
    """Raised with safe details for fallback decisions."""

    def __init__(self, message, fallback_allowed=False, failure_reason=None):
        super().__init__(message)
        self.fallback_allowed = fallback_allowed
        self.failure_reason = failure_reason


def build_messages(history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(
        {"role": message["role"], "content": message["content"]}
        for message in history
        if message["role"] in {"user", "assistant"}
    )
    return messages


def extract_reply(data):
    if not isinstance(data, dict):
        raise GroqChatError("The AI returned an unreadable answer. Please try again.")
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    if not isinstance(choice, dict):
        raise GroqChatError("The AI returned an unreadable answer. Please try again.")
    message = choice.get("message") or {}
    if not isinstance(message, dict):
        raise GroqChatError("The AI returned an unreadable answer. Please try again.")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if choice.get("finish_reason") == "length":
        raise GroqChatError("The model ran out of tokens")
    raise GroqChatError("The AI returned an empty answer. Please try again.")


def generate_reply(history, api_key=None, model=None, timeout=45):
    api_key = settings.GROQ_API_KEY if api_key is None else api_key
    model = settings.GROQ_CHAT_MODEL if model is None else model
    if not api_key:
        raise GroqChatError("The Groq chat provider is not configured.")

    reasoning_effort = settings.GROQ_CHAT_REASONING_EFFORT
    try:
        response = chat_completion(
            messages=build_messages(history),
            api_key=api_key,
            model=model,
            timeout=timeout,
            max_tokens=settings.GROQ_CHAT_MAX_TOKENS,
            temperature=0.6,
            reasoning_effort=reasoning_effort,
            include_reasoning=False if model in REASONING_EFFORT_MODELS else None,
            reasoning_effort_setting_name="GROQ_CHAT_REASONING_EFFORT",
        )
    except GroqTransportError as exc:
        raise GroqChatError(
            "Could not reach the AI service. Please try again.",
            fallback_allowed=True,
            failure_reason=type(exc.__cause__).__name__ if exc.__cause__ else "network error",
        ) from exc
    except ValueError as exc:
        raise GroqChatError(str(exc)) from exc

    if response.status_code == 429:
        raise GroqChatError(
            "The AI service is busy or its quota is used up. Try again in a minute.",
            fallback_allowed=True,
            failure_reason="HTTP 429",
        )
    if response.status_code in (400, 401, 403, 404):
        logger.error("Groq chat rejected the request with status %s", response.status_code)
        raise GroqChatError(
            "The AI service rejected the request. Check the API key and model name.",
            failure_reason=f"HTTP {response.status_code}",
        )
    if response.status_code >= 400:
        logger.error("Groq chat returned HTTP status %s", response.status_code)
        raise GroqChatError(
            "The AI service had a problem. Please try again.",
            fallback_allowed=response.status_code >= 500,
            failure_reason=f"HTTP {response.status_code}",
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise GroqChatError("The AI returned an unreadable answer. Please try again.") from exc
    return extract_reply(data).replace(api_key, "[REDACTED]")
