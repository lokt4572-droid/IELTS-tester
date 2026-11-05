"""Provider registry and selection for chat replies."""

import logging

from django.conf import settings

from .gemini import GeminiError, generate_reply as generate_gemini_reply
from .groq import GroqChatError, generate_reply as generate_groq_reply

logger = logging.getLogger(__name__)

PROVIDERS = ("groq", "gemini")


def is_available(provider):
    if provider == "groq":
        return bool(settings.GROQ_API_KEY)
    if provider == "gemini":
        return bool(settings.GEMINI_API_KEY)
    return False


class ChatProviderError(Exception):
    """A provider failure with a safe message for the chat endpoint."""


def generate_chat_reply(messages, provider):
    if provider not in PROVIDERS:
        logger.error("Configured chat provider is invalid")
        raise ChatProviderError("The AI tutor is unavailable right now. Please try again later.")
    if not is_available(provider):
        logger.error("Configured chat provider is not available")
        raise ChatProviderError("The AI tutor is not configured right now.")

    generate = {
        "groq": generate_groq_reply,
        "gemini": generate_gemini_reply,
    }

    def safe_reply(provider_name):
        reply = generate[provider_name](messages)
        api_key = (
            settings.GROQ_API_KEY
            if provider_name == "groq"
            else settings.GEMINI_API_KEY
        )
        return reply.replace(api_key, "[REDACTED]") if api_key else reply

    try:
        return safe_reply(provider), provider, None
    except GroqChatError as primary_error:
        if (
            provider == "groq"
            and settings.CHAT_AI_FALLBACK_FROM_GROQ
            and is_available("gemini")
            and getattr(primary_error, "fallback_allowed", False)
        ):
            reason = getattr(primary_error, "failure_reason", "provider error")
            logger.warning("Chat provider fallback from groq to gemini (%s)", reason)
            try:
                return safe_reply("gemini"), "gemini", "groq"
            except GeminiError as fallback_error:
                logger.error(
                    "Chat backup provider failed (%s)",
                    getattr(fallback_error, "failure_reason", "provider error"),
                )
                raise ChatProviderError(
                    "The AI tutor is busy right now. Please try again in a moment."
                ) from fallback_error
        if not getattr(primary_error, "fallback_allowed", False):
            logger.error(
                "Groq chat configuration request failed (%s)",
                getattr(primary_error, "failure_reason", "provider error"),
            )
            raise ChatProviderError(
                "The AI tutor could not process this request. Please try again later."
            ) from primary_error
        raise ChatProviderError(
            "The AI tutor is busy right now. Please try again in a moment."
        ) from primary_error
    except GeminiError as primary_error:
        raise ChatProviderError(
            "The AI tutor is busy right now. Please try again in a moment."
        ) from primary_error
