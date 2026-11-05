import json

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.views.csrf import csrf_failure as default_csrf_failure
from django.views.decorators.http import require_POST

from .evaluation_service import (
    EvaluationLimitReached,
    EvaluationServiceError,
    MINIMUM_EVALUATION_WORDS,
    TOO_SHORT_ERROR,
    evaluate_writing_response,
    evaluations_used_today,
    overall_band_estimate,
    validate_language,
)
from .models import WritingAttempt, WritingEvaluation, WritingResponse, WritingTest
from .scoring import count_words


def test_list(request):
    tests = WritingTest.objects.filter(is_published=True).order_by("title")
    return render(request, "writing/test_list.html", {"tests": tests})


def test_detail(request, slug):
    test = get_object_or_404(WritingTest, slug=slug, is_published=True)
    tasks = list(test.tasks.all())
    return render(request, "writing/test_detail.html", {"test": test, "tasks": tasks})


@login_required
@require_POST
def start_attempt(request, slug):
    test = get_object_or_404(WritingTest, slug=slug, is_published=True)
    mode = request.POST.get("mode", "exam")
    if mode not in {"exam", "practice"}:
        mode = "exam"

    existing = (
        WritingAttempt.objects.filter(user=request.user, test=test, status="in_progress")
        .order_by("-started_at")
        .first()
    )
    if existing:
        if existing.mode != mode:
            existing.mode = mode
            existing.save(update_fields=["mode"])
        return redirect("writing:attempt", pk=existing.pk)

    attempt = WritingAttempt.objects.create(user=request.user, test=test, mode=mode)
    for task in test.tasks.all():
        WritingResponse.objects.create(attempt=attempt, task=task, text="", word_count=0)
    return redirect("writing:attempt", pk=attempt.pk)


def _own_attempt(request, pk):
    return get_object_or_404(
        WritingAttempt.objects.select_related("test").prefetch_related("responses__task"),
        pk=pk,
        user=request.user,
    )


def csrf_failure(request, reason=""):
    try:
        is_evaluation_endpoint = resolve(request.path_info).view_name == "writing:evaluate"
    except Resolver404:
        is_evaluation_endpoint = False
    if is_evaluation_endpoint:
        return JsonResponse({"error": "CSRF verification failed."}, status=403)
    return default_csrf_failure(request, reason=reason)


@login_required
def attempt_page(request, pk):
    attempt = _own_attempt(request, pk)

    if attempt.status == "submitted":
        return redirect("writing:result", pk=attempt.pk)
    if attempt.is_expired():
        attempt.status = "expired"
        attempt.submitted_at = timezone.now()
        attempt.save(update_fields=["status", "submitted_at"])
        return redirect("writing:result", pk=attempt.pk)

    tasks = list(attempt.test.tasks.all())
    response_map = {}
    for response in attempt.responses.select_related("task").all():
        response_map[response.task_id] = response.text

    return render(request, "writing/attempt.html", {
        "attempt": attempt,
        "tasks": tasks,
        "response_map": response_map,
    })


@login_required
@require_POST
def attempt_save(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status == "submitted":
        return JsonResponse({"ok": False, "finished": True}, status=409)

    updated = []
    for task in attempt.test.tasks.all():
        text = request.POST.get(f"response_{task.id}", "")
        response = attempt.responses.filter(task=task).first()
        if response is None:
            response = WritingResponse.objects.create(attempt=attempt, task=task, text=text)
        else:
            response.text = text
            response.save()
        updated.append(response.text)

    return JsonResponse({"ok": True, "saved": len(updated), "answered": sum(1 for value in updated if value.strip())})


@login_required
@require_POST
def attempt_submit(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status != "submitted":
        for task in attempt.test.tasks.all():
            text = request.POST.get(f"response_{task.id}", "")
            response = attempt.responses.filter(task=task).first()
            if response is None:
                response = WritingResponse.objects.create(attempt=attempt, task=task, text=text)
            else:
                response.text = text
                response.save()
        attempt.status = "submitted"
        attempt.submitted_at = timezone.now()
        attempt.save(update_fields=["status", "submitted_at"])
        messages.success(request, "Your writing responses have been submitted.")
    return redirect("writing:result", pk=attempt.pk)


@login_required
def attempt_result(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status != "submitted" and attempt.status != "expired":
        return redirect("writing:attempt", pk=attempt.pk)
    evaluations = WritingEvaluation.objects.filter(status="completed").order_by("-created_at")
    response_rows = list(
        attempt.responses.select_related("task", "score")
        .prefetch_related(
            Prefetch(
                "ai_evaluations",
                queryset=evaluations,
                to_attr="completed_ai_evaluations",
            )
        )
        .all()
    )
    for response in response_rows:
        response.has_response = bool(response.text.strip())
        response.existing_ai_evaluation = (
            response.completed_ai_evaluations[0]
            if response.completed_ai_evaluations
            else None
        )
        response.ai_json_id = f"wr-existing-evaluation-{response.task.task_number}"

    ai_evaluation_enabled = bool(settings.GROQ_API_KEY)
    current_overall_band = (
        overall_band_estimate(attempt) if ai_evaluation_enabled else None
    )
    return render(request, "writing/attempt_result.html", {
        "attempt": attempt,
        "response_rows": response_rows,
        "ai_evaluation_enabled": ai_evaluation_enabled,
        "evaluate_url": reverse("writing:evaluate", args=[attempt.pk]),
        "overall_band_estimate": current_overall_band,
        "overall_band_available": current_overall_band is not None,
    })


def evaluate_attempt_response(request, pk):
    if request.method != "POST":
        response = JsonResponse({"error": "Method not allowed."}, status=405)
        response["Allow"] = "POST"
        return response
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication is required."}, status=401)
    if request.content_type != "application/json":
        return JsonResponse({"error": "Content-Type must be application/json."}, status=415)
    try:
        attempt = _own_attempt(request, pk)
    except Http404:
        return JsonResponse({"error": "Attempt not found."}, status=404)
    if attempt.status not in {"submitted", "expired"}:
        return JsonResponse({"error": "Submit the attempt before requesting an evaluation."}, status=409)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON request body."}, status=400)
    if not isinstance(payload, dict) or set(payload) - {"task_number", "language"}:
        return JsonResponse({"error": "A JSON object with task_number and optional language is required."}, status=400)
    task_number = payload.get("task_number")
    language = payload.get("language", "en")
    if isinstance(task_number, bool) or not isinstance(task_number, (str, int)):
        return JsonResponse({"error": "A valid task_number is required."}, status=400)
    try:
        task_number = int(task_number)
    except (TypeError, ValueError):
        return JsonResponse({"error": "A valid task_number is required."}, status=400)
    if task_number not in {1, 2}:
        return JsonResponse({"error": "task_number must be 1 or 2."}, status=400)
    try:
        validate_language(language)
    except ValueError:
        return JsonResponse({"error": "language must be 'en', 'ru', or 'tg'."}, status=400)

    response = get_object_or_404(
        WritingResponse.objects.select_related("task", "attempt__test"),
        attempt=attempt,
        task__task_number=task_number,
    )
    if count_words(response.text) < MINIMUM_EVALUATION_WORDS:
        return JsonResponse(
            {"error": TOO_SHORT_ERROR, "too_short": True},
            status=400,
        )
    try:
        result = evaluate_writing_response(response, language)
    except EvaluationLimitReached as exc:
        return JsonResponse({
            "error": str(exc),
            "remaining_today": 0,
        }, status=429)
    except EvaluationServiceError as exc:
        remaining = max(
            0,
            settings.GROQ_EVALUATIONS_DAILY_LIMIT - evaluations_used_today(request.user),
        )
        return JsonResponse({
            "error": str(exc),
            "remaining_today": remaining,
            **({"too_short": True} if exc.too_short else {}),
        }, status=exc.status_code)

    return JsonResponse({"ok": True, **result})


@staff_member_required
def attempt_preview(request, pk):
    attempt = get_object_or_404(
        WritingAttempt.objects.select_related("user", "test").prefetch_related("responses__task"),
        pk=pk,
    )
    response_rows = list(attempt.responses.select_related("task").all())
    return render(request, "writing/admin_attempt_preview.html", {
        "attempt": attempt,
        "response_rows": response_rows,
    })
