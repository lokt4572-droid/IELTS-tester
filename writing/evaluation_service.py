"""Shared caching, quota, and provider orchestration for Writing evaluations."""

import hashlib
import json
import time
from datetime import datetime, time as day_time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .evaluation_validation import (
    VALIDATION_VERSION,
    EvaluationValidationError,
    validate_evaluation,
)
from .evaluator_prompt import LANGUAGE_NAMES, PROMPT_VERSION
from .groq import GroqError, evaluate_response
from .models import WritingEvaluation
from .scoring import count_words, writing_band

MINIMUM_EVALUATION_WORDS = 20
TOO_SHORT_ERROR = "Text is too short to evaluate (minimum 20 words)"


class EvaluationServiceError(Exception):
    def __init__(
        self,
        message,
        status_code=502,
        validation_error=None,
        diagnostics=None,
        too_short=False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.validation_error = validation_error
        self.diagnostics = diagnostics
        self.too_short = too_short


class EvaluationLimitReached(EvaluationServiceError):
    def __init__(self):
        super().__init__(
            "You have reached today's Writing evaluation limit. It resets at midnight.",
            status_code=429,
        )


def validate_language(language):
    if not isinstance(language, str) or language not in LANGUAGE_NAMES:
        raise ValueError("language must be 'en', 'ru', or 'tg'")
    return language


def evaluation_request_hash(response, language):
    request_data = {
        "prompt_version": PROMPT_VERSION,
        "validation_version": VALIDATION_VERSION,
        "model": settings.GROQ_MODEL,
        "fallback_model": settings.GROQ_FALLBACK_MODEL,
        "max_tokens": settings.GROQ_MAX_TOKENS,
        "reasoning_effort": settings.GROQ_REASONING_EFFORT,
        "module": response.attempt.test.module,
        "task_number": response.task.task_number,
        "task_prompt": response.task.prompt_text,
        "response": response.text,
        "language": language,
    }
    canonical = json.dumps(request_data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evaluations_used_today(user):
    today = timezone.localdate()
    midnight = timezone.make_aware(datetime.combine(today, day_time.min))
    return WritingEvaluation.objects.filter(
        response__attempt__user=user,
        created_at__gte=midnight,
        status="completed",
    ).count()


def overall_band_estimate(attempt):
    task_bands = {}
    responses = attempt.responses.select_related("task").filter(
        task__task_number__in=(1, 2)
    )
    for response in responses:
        valid_hashes = [
            evaluation_request_hash(response, language)
            for language in LANGUAGE_NAMES
        ]
        evaluation = (
            WritingEvaluation.objects.filter(
                response=response,
                request_hash__in=valid_hashes,
                status="completed",
            )
            .order_by("-created_at")
            .first()
        )
        if evaluation is None:
            continue
        task_bands[response.task.task_number] = evaluation.result["task_band_estimate"]

    if 1 not in task_bands or 2 not in task_bands:
        return None
    return writing_band(task_bands[1], task_bands[2])


def evaluate_writing_response(response, language="en", debug=False):
    validate_language(language)
    if count_words(response.text) < MINIMUM_EVALUATION_WORDS:
        raise EvaluationServiceError(
            TOO_SHORT_ERROR,
            status_code=400,
            too_short=True,
        )
    if not settings.GROQ_API_KEY:
        raise EvaluationServiceError("The Writing evaluator is not configured.", status_code=503)

    request_hash = evaluation_request_hash(response, language)
    failure = None
    result = None
    with transaction.atomic():
        user_model = get_user_model()
        user_model.objects.select_for_update().get(pk=response.attempt.user_id)

        cached = WritingEvaluation.objects.filter(
            response=response,
            request_hash=request_hash,
            status="completed",
        ).first()
        used_today = evaluations_used_today(response.attempt.user)
        remaining = max(0, settings.GROQ_EVALUATIONS_DAILY_LIMIT - used_today)
        if cached is not None:
            return {
                "evaluation": cached.result,
                "cached": True,
                "remaining_today": remaining,
                "latency_ms": 0,
                "overall_band_estimate": overall_band_estimate(response.attempt),
            }
        if remaining == 0:
            raise EvaluationLimitReached()

        record = WritingEvaluation.objects.create(
            response=response,
            request_hash=request_hash,
            status="failed",
        )
        started = time.monotonic()
        try:
            provider_result = evaluate_response(
                response.task.task_number,
                response.task.prompt_text,
                response.text,
                module=response.attempt.test.module,
                language=language,
                model=settings.GROQ_MODEL,
                fallback_model=settings.GROQ_FALLBACK_MODEL,
                include_metadata=debug,
            )
            if debug:
                raw_result, diagnostics = provider_result
            else:
                raw_result, diagnostics = provider_result, None
            try:
                normalized_result = validate_evaluation(
                    json.loads(raw_result),
                    learner_response=response.text,
                )
            except (json.JSONDecodeError, EvaluationValidationError) as exc:
                validation_error = str(exc)
                record.error_message = validation_error[:300]
                record.save(update_fields=["error_message"])
                failure = EvaluationServiceError(
                    "The Writing evaluator returned an invalid assessment.",
                    validation_error=validation_error,
                    diagnostics=diagnostics,
                )
        except GroqError as exc:
            validation_error = exc.validation_error
            record.error_message = (
                validation_error or str(exc)
            )[:300]
            record.save(update_fields=["error_message"])
            failure = EvaluationServiceError(
                str(exc),
                validation_error=validation_error,
                diagnostics=exc.diagnostics,
            )

        if failure is None:
            latency_ms = round((time.monotonic() - started) * 1000)
            record.status = "completed"
            record.result = normalized_result
            record.save(update_fields=["status", "result"])
            used_today = evaluations_used_today(response.attempt.user)
            result = {
                "evaluation": normalized_result,
                "cached": False,
                "remaining_today": max(0, settings.GROQ_EVALUATIONS_DAILY_LIMIT - used_today),
                "latency_ms": latency_ms,
                "overall_band_estimate": overall_band_estimate(response.attempt),
            }

    if failure is not None:
        raise failure
    return result
