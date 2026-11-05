"""Groq chat-completions client with bounded retries and safe errors."""

import json
import logging
import time
from dataclasses import dataclass

from core.ai import groq_transport
from .evaluator_prompt import build_evaluation_messages

logger = logging.getLogger(__name__)

API_URL = groq_transport.API_URL
RETRY_DELAYS = groq_transport.RETRY_DELAYS
REASONING_EFFORT_MODELS = groq_transport.REASONING_EFFORT_MODELS


class GroqError(Exception):
    """Raised with a message that is safe to show to the student."""

    def __init__(
        self,
        message,
        retryable=False,
        validation_error=None,
        diagnostics=None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.validation_error = validation_error
        self.diagnostics = diagnostics


@dataclass
class GroqResponse:
    content: str
    model: str
    status_code: int
    finish_reason: str
    usage: object
    reasoning: str

    @property
    def debug_reply(self):
        if self.reasoning:
            return f"{self.content}\n\n{self.reasoning}"
        return self.content


def _retry_after_seconds(response):
    return groq_transport._retry_after_seconds(response)


def _post_once(messages, api_key, model, timeout):
    from django.conf import settings

    return groq_transport.chat_completion(
        messages=messages,
        api_key=api_key,
        model=model,
        timeout=timeout,
        max_tokens=settings.GROQ_MAX_TOKENS,
        temperature=0.2,
        response_format={"type": "json_object"},
        reasoning_effort=settings.GROQ_REASONING_EFFORT,
        retries=False,
    )


def _reply_from_response(response, model, api_key):
    if response.status_code == 429 or response.status_code >= 500:
        raise GroqError(
            "The Writing evaluation service is temporarily unavailable. Please try again.",
            retryable=True,
        )
    if response.status_code >= 400:
        logger.error("Groq rejected the Writing evaluation request with status %s", response.status_code)
        raise GroqError("The Writing evaluation service rejected the request. Check the API key and model name.")
    try:
        data = response.json()
    except ValueError:
        raise GroqError("The Writing evaluator returned an unreadable answer. Please try again.")
    choices = data.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    finish_reason = choices[0].get("finish_reason") if choices else None
    if finish_reason == "length":
        raise GroqError(
            "The model ran out of tokens; increase GROQ_MAX_TOKENS",
            retryable=True,
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GroqError("The Writing evaluator returned an empty answer. Please try again.")
    reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
    if not isinstance(reasoning, str):
        reasoning = json.dumps(reasoning, ensure_ascii=False)
    # Avoid ever exposing a configured credential if a model repeats input text.
    raw_content = content.replace(api_key, "[REDACTED]") if api_key else content
    reasoning = reasoning.replace(api_key, "[REDACTED]") if api_key else reasoning
    return GroqResponse(
        content=raw_content.strip(),
        model=model,
        status_code=response.status_code,
        finish_reason=finish_reason or "not provided",
        usage=data.get("usage"),
        reasoning=reasoning.strip(),
    )


def _complete_once(messages, api_key, model, timeout):
    try:
        response = _post_once(messages, api_key, model, timeout)
    except groq_transport.GroqTransportError as exc:
        logger.error("Groq transport failed (%s)", type(exc).__name__)
        raise GroqError(
            "Could not reach the Writing evaluation service. Please try again.",
            retryable=True,
        )
    return _reply_from_response(response, model, api_key)


def _complete_with_retries(messages, api_key, model, timeout):
    from django.conf import settings

    try:
        response = groq_transport.chat_completion(
            messages=messages,
            api_key=api_key,
            model=model,
            timeout=timeout,
            max_tokens=settings.GROQ_MAX_TOKENS,
            temperature=0.2,
            response_format={"type": "json_object"},
            reasoning_effort=settings.GROQ_REASONING_EFFORT,
            retries=True,
        )
    except groq_transport.GroqTransportError as exc:
        logger.error("Groq transport failed after retries (%s)", type(exc).__name__)
        raise GroqError(
            "Could not reach the Writing evaluation service. Please try again.",
            retryable=True,
        ) from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise GroqError(
            "The Writing evaluation service is temporarily unavailable. Please try again.",
            retryable=True,
        )
    if response.status_code >= 400:
        logger.error("Groq rejected the Writing evaluation request with status %s", response.status_code)
        raise GroqError("The Writing evaluation service rejected the request. Check the API key and model name.")
    return _reply_from_response(response, model, api_key)


def _complete_as_json(messages, api_key, model, timeout, retries=True, repair_json=True):
    complete = _complete_with_retries if retries else _complete_once
    reply = complete(messages, api_key, model, timeout)
    try:
        json.loads(reply.content)
        return reply
    except json.JSONDecodeError as exc:
        if not repair_json:
            raise GroqError(
                "The Writing evaluator returned invalid JSON.",
                validation_error=str(exc),
                diagnostics=reply,
            ) from exc
        repair_messages = messages + [{
            "role": "user",
            "content": "Return only valid JSON that matches the schema",
        }]
    reply = complete(repair_messages, api_key, model, timeout)
    try:
        json.loads(reply.content)
    except json.JSONDecodeError as exc:
        raise GroqError(
            "The Writing evaluator returned invalid JSON after a repair attempt.",
            validation_error=str(exc),
            diagnostics=reply,
        ) from exc
    return reply


def evaluate_response(
    task_number,
    task_prompt,
    response,
    module="academic",
    language="en",
    api_key=None,
    model=None,
    fallback_model=None,
    timeout=45,
    include_metadata=False,
):
    if api_key is None or model is None or fallback_model is None:
        from django.conf import settings

        api_key = settings.GROQ_API_KEY if api_key is None else api_key
        model = settings.GROQ_MODEL if model is None else model
        fallback_model = settings.GROQ_FALLBACK_MODEL if fallback_model is None else fallback_model
    if not api_key:
        raise GroqError("The Writing evaluator is not configured.")

    messages = build_evaluation_messages(task_number, task_prompt, response, module, language)
    try:
        result = _complete_as_json(messages, api_key, model, timeout)
    except GroqError as primary_error:
        if not primary_error.retryable or not fallback_model or fallback_model == model:
            raise primary_error
        try:
            result = _complete_as_json(
                messages,
                api_key,
                fallback_model,
                timeout,
                retries=False,
                repair_json=False,
            )
        except GroqError:
            raise primary_error
    if include_metadata:
        return result.content, result
    return result.content
