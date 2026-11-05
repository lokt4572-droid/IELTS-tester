import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .checking import check_answer, check_mcq_multi
from .models import ListeningAnswer, ListeningAttempt, ListeningQuestion, ListeningTest
from .phase import build_schedule, phase_at
from .scoring import listening_band


class AnswerPayloadError(ValueError):
    pass


def test_list(request):
    tests = (
        ListeningTest.objects.filter(is_published=True)
        .annotate(
            n_sections=Count("sections", distinct=True),
            n_questions=Count("questions", distinct=True),
        )
        .order_by("title")
    )
    if request.user.is_authenticated:
        attempts = ListeningAttempt.objects.filter(
            user=request.user,
            test__is_published=True,
            status="in_progress",
        ).order_by("-started_at")
        resume_by_test = {}
        for attempt in attempts:
            resume_by_test.setdefault(attempt.test_id, attempt)
        for test in tests:
            test.resume_attempt = resume_by_test.get(test.pk)
    return render(request, "listening/test_list.html", {"tests": tests})


def test_detail(request, slug):
    test = get_object_or_404(ListeningTest, slug=slug, is_published=True)
    sections = list(test.sections.prefetch_related("groups__questions"))
    for section in sections:
        section.n_questions = sum(group.questions.count() for group in section.groups.all())
    resume_attempt = None
    if request.user.is_authenticated:
        resume_attempt = (
            ListeningAttempt.objects.filter(
                user=request.user,
                test=test,
                status="in_progress",
            )
            .order_by("-started_at")
            .first()
        )
    return render(request, "listening/test_detail.html", {
        "test": test,
        "sections": sections,
        "n_questions": test.question_count(),
        "resume_attempt": resume_attempt,
        "review_duration": (
            f"{test.review_seconds // 60} minutes"
            if test.review_seconds % 60 == 0
            else f"{test.review_seconds} seconds"
        ),
    })


@login_required
@require_POST
def start_attempt(request, slug):
    test = get_object_or_404(ListeningTest, slug=slug, is_published=True)
    mode = request.POST.get("mode")
    if mode not in {"exam", "practice"}:
        mode = "exam"

    attempt = (
        ListeningAttempt.objects.filter(
            user=request.user,
            test=test,
            status="in_progress",
        )
        .order_by("-started_at")
        .first()
    )
    if attempt is None:
        attempt = ListeningAttempt.objects.create(
            user=request.user,
            test=test,
            mode=mode,
        )

    if attempt.mode == "exam":
        return redirect("listening:sound_check", pk=attempt.pk)
    return redirect("listening:attempt", pk=attempt.pk)


def _own_attempt(request, pk):
    return get_object_or_404(
        ListeningAttempt.objects.select_related("test"),
        pk=pk,
        user=request.user,
    )


@login_required
@require_GET
def sound_check(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status != "in_progress":
        return redirect("listening:detail", slug=attempt.test.slug)
    if attempt.mode != "exam":
        return redirect("listening:attempt", pk=attempt.pk)
    return render(request, "listening/sound_check.html", {"attempt": attempt})


@login_required
@require_POST
def confirm_sound_check(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status != "in_progress":
        return redirect("listening:detail", slug=attempt.test.slug)
    if attempt.mode != "exam":
        return redirect("listening:attempt", pk=attempt.pk)
    return redirect("listening:attempt", pk=attempt.pk)


@login_required
def attempt_page(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status != "in_progress":
        if attempt.status == "submitted":
            return redirect("listening:result", pk=attempt.pk)
        return redirect("listening:detail", slug=attempt.test.slug)
    if attempt.mode == "exam":
        if attempt.exam_started_at and phase_at(attempt)["phase"] == "finished":
            _finalize_if_active(attempt.pk)
            return redirect("listening:result", pk=attempt.pk)
        sections, answer_map, saved_at = _attempt_content(attempt)
        return render(request, "listening/attempt_exam.html", {
            "attempt": attempt,
            "sections": sections,
            "answer_map": answer_map,
            "saved_at": saved_at.isoformat() if saved_at else "",
            "schedule": build_schedule(attempt),
            "server_now": timezone.now().isoformat(),
            "audio_map": {
                str(section.number): section.audio.url
                for section in sections
            },
        })

    sections, answer_map, saved_at = _attempt_content(attempt)
    all_questions = list(
        ListeningQuestion.objects.filter(test=attempt.test)
        .select_related("group", "group__section")
        .order_by("number")
    )
    return render(request, "listening/attempt_practice.html", {
        "attempt": attempt,
        "sections": sections,
        "questions": all_questions,
        "answer_map": answer_map,
        "saved_at": saved_at.isoformat() if saved_at else "",
    })


def _attempt_content(attempt):
    sections = list(
        attempt.test.sections.prefetch_related("groups__questions").order_by("number")
    )
    questions = list(
        ListeningQuestion.objects.filter(test=attempt.test)
        .select_related("group")
        .order_by("number")
    )
    answer_rows = {
        answer.question_number: answer
        for answer in ListeningAnswer.objects.filter(attempt=attempt)
    }
    answer_map = {}
    for question in questions:
        answer = answer_rows.get(question.number)
        if question.group.qtype == "mcq_multi":
            answer_map[str(question.number)] = (
                [letter for letter in answer.value.split(",") if letter]
                if answer else []
            )
        else:
            answer_map[str(question.number)] = answer.value if answer else ""
    saved_at = ListeningAnswer.objects.filter(attempt=attempt).aggregate(
        latest=Max("updated_at")
    )["latest"]
    for section in sections:
        section.question_count = sum(group.questions.count() for group in section.groups.all())
        section.answered_count = sum(
            bool(answer_map.get(str(question.number)))
            for group in section.groups.all()
            for question in group.questions.all()
        )
    return sections, answer_map, saved_at


def _finish_attempt(attempt):
    questions = list(
        ListeningQuestion.objects.filter(test=attempt.test)
        .select_related("group")
        .order_by("number")
    )
    answers = {
        answer.question_number: answer
        for answer in ListeningAnswer.objects.filter(attempt=attempt)
    }
    raw_score = 0
    for question in questions:
        answer = answers.get(question.number)
        given = answer.value if answer else ""
        if question.group.qtype == "mcq_multi":
            is_correct = bool(check_mcq_multi([question.answer], given.split(",")))
        else:
            is_correct = check_answer(given, question.answer, question.group.qtype)
        if answer is None:
            answer = ListeningAnswer(
                attempt=attempt,
                question_number=question.number,
                value="",
            )
        answer.is_correct = is_correct
        answer.save()
        raw_score += int(is_correct)
    attempt.raw_score = raw_score
    attempt.band = listening_band(raw_score, len(questions))
    attempt.status = "submitted"
    attempt.submitted_at = timezone.now()
    attempt.save(update_fields=["raw_score", "band", "status", "submitted_at"])


def _finalize_if_active(attempt_id):
    with transaction.atomic():
        attempt = (
            ListeningAttempt.objects.select_for_update()
            .select_related("test")
            .get(pk=attempt_id)
        )
        if attempt.status != "in_progress":
            return attempt
        _finish_attempt(attempt)
        return attempt


def _phase_payload(attempt, now=None):
    now = now or timezone.now()
    return {
        **phase_at(attempt, now),
        "schedule": build_schedule(attempt),
        "server_now": now.isoformat(),
    }


def _finished_response(attempt):
    return JsonResponse({
        "ok": True,
        "finished": True,
        "result_url": redirect("listening:result", pk=attempt.pk).url,
        "server_now": timezone.now().isoformat(),
    })


@login_required
@require_POST
def exam_begin(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.mode != "exam":
        return JsonResponse({"ok": False, "error": "Only exam mode can be begun here."}, status=400)
    with transaction.atomic():
        attempt = ListeningAttempt.objects.select_for_update().select_related("test").get(pk=pk)
        if attempt.status != "in_progress":
            return JsonResponse({"ok": False, "error": "This attempt is not in progress."}, status=409)
        if attempt.exam_started_at is None:
            attempt.exam_started_at = timezone.now()
            attempt.save(update_fields=["exam_started_at"])
    now = timezone.now()
    current = _phase_payload(attempt, now)
    if current["phase"] == "finished":
        attempt = _finalize_if_active(attempt.pk)
        return _finished_response(attempt)
    return JsonResponse({"ok": True, **current})


@login_required
@require_GET
def exam_state(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.mode != "exam":
        return JsonResponse({"ok": False, "error": "This is not an exam attempt."}, status=400)
    if attempt.status == "submitted":
        return _finished_response(attempt)
    if attempt.status != "in_progress":
        return JsonResponse({"ok": False, "error": "This attempt is not in progress."}, status=409)
    now = timezone.now()
    state = _phase_payload(attempt, now)
    if state["phase"] == "finished":
        attempt = _finalize_if_active(attempt.pk)
        return _finished_response(attempt)
    return JsonResponse({"ok": True, **state})


def _json_body(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnswerPayloadError("Request body must contain valid JSON.") from exc
    if not isinstance(payload, dict):
        raise AnswerPayloadError("Request body must be a JSON object.")
    answers = payload.get("answers")
    if not isinstance(answers, dict):
        raise AnswerPayloadError("'answers' must be an object keyed by question number.")
    return answers


def _validated_answers(attempt, raw_answers):
    questions = {
        str(question.number): question
        for question in ListeningQuestion.objects.filter(test=attempt.test)
        .select_related("group")
    }
    validated = {}
    multi_group_values = {}
    for raw_number, raw_value in raw_answers.items():
        if not isinstance(raw_number, str) or raw_number not in questions:
            raise AnswerPayloadError(f"Unknown question number: {raw_number}.")
        question = questions[raw_number]
        group = question.group
        qtype = group.qtype
        options = question.options or group.options
        valid_letters = {
            option.get("key", "").upper()
            for option in options
            if isinstance(option, dict) and isinstance(option.get("key"), str)
        }

        if qtype == "mcq_multi":
            if not isinstance(raw_value, list):
                raise AnswerPayloadError(f"Question {raw_number} requires a list of letters.")
            letters = []
            for letter in raw_value:
                if not isinstance(letter, str) or len(letter) != 1:
                    raise AnswerPayloadError(f"Question {raw_number} has an invalid letter.")
                normalized = letter.upper()
                if normalized not in valid_letters:
                    raise AnswerPayloadError(
                        f"Question {raw_number} contains a letter outside its options."
                    )
                if normalized in letters:
                    raise AnswerPayloadError(f"Question {raw_number} has a duplicate letter.")
                letters.append(normalized)
            if len(letters) > (group.choose or 0):
                raise AnswerPayloadError(
                    f"Choose no more than {group.choose} letters for question {raw_number}."
                )
            value = ",".join(sorted(letters))
            previous = multi_group_values.get(group.pk)
            if previous is not None and previous != value:
                raise AnswerPayloadError(
                    f"Questions in the same choose-{group.choose} group must share one answer set."
                )
            multi_group_values[group.pk] = value
        elif qtype in {"mcq", "matching", "diagram_label"}:
            if not isinstance(raw_value, str):
                raise AnswerPayloadError(f"Question {raw_number} must be one letter.")
            value = raw_value.strip().upper()
            if value and (
                len(value) != 1 or value not in valid_letters
            ):
                raise AnswerPayloadError(
                    f"Question {raw_number} must use one of its listed option letters."
                )
        else:
            if not isinstance(raw_value, str):
                raise AnswerPayloadError(f"Question {raw_number} must be text.")
            if len(raw_value) > 200:
                raise AnswerPayloadError(
                    f"Question {raw_number} must be no more than 200 characters."
                )
            value = raw_value
        validated[question.number] = value
    for group_id, value in multi_group_values.items():
        for question_number in questions.values():
            if question_number.group_id == group_id:
                validated[question_number.number] = value
    return validated, questions


def _save_answer_values(attempt, values):
    for question_number, value in values.items():
        ListeningAnswer.objects.update_or_create(
            attempt=attempt,
            question_number=question_number,
            defaults={"value": value, "is_correct": None},
        )


@login_required
@require_POST
def attempt_save(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status != "in_progress":
        return JsonResponse(
            {"ok": False, "error": "This attempt has already been submitted."},
            status=409,
        )
    if attempt.mode != "practice":
        if attempt.exam_started_at is None:
            return JsonResponse(
                {"ok": False, "error": "The exam has not begun yet."},
                status=409,
            )
        current_state = phase_at(attempt)
        if current_state["phase"] == "finished":
            attempt = _finalize_if_active(attempt.pk)
            return _finished_response(attempt)
    try:
        validated, _ = _validated_answers(attempt, _json_body(request))
    except AnswerPayloadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    with transaction.atomic():
        locked = ListeningAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status != "in_progress":
            return JsonResponse(
                {"ok": False, "error": "This attempt has already been submitted."},
                status=409,
            )
        if locked.mode == "exam":
            now = timezone.now()
            state = phase_at(locked, now)
            if state["phase"] == "finished":
                _finish_attempt(locked)
                return _finished_response(locked)
            if state["phase"] not in {"preview", "listen", "check", "review"}:
                return JsonResponse({
                    "ok": False,
                    "error": "Answers cannot be saved before the exam timeline begins.",
                    **_phase_payload(locked, now),
                }, status=409)
            questions_by_number = {
                question.number: question
                for question in ListeningQuestion.objects.filter(test=locked.test)
                .select_related("group__section")
            }
            allowed_section = state["section_number"]
            for question_number in validated:
                question = questions_by_number[question_number]
                if state["phase"] != "review" and (
                    question.group.section.number != allowed_section
                ):
                    return JsonResponse({
                        "ok": False,
                        "error": (
                            f"Question {question_number} is not editable in the current "
                            "exam phase."
                        ),
                    }, status=409)
        attempt = locked
        _save_answer_values(locked, validated)
    response_data = {
        "ok": True,
        "saved_at": timezone.now().isoformat(),
        "saved": len(validated),
    }
    if attempt.mode == "exam":
        now = timezone.now()
        state = _phase_payload(attempt, now)
        if state["phase"] == "finished":
            attempt = _finalize_if_active(attempt.pk)
            return _finished_response(attempt)
        response_data.update(state)
    return JsonResponse(response_data)


@login_required
@require_POST
def attempt_submit(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status == "submitted":
        return redirect("listening:result", pk=attempt.pk)
    if attempt.mode != "practice":
        return JsonResponse(
            {"ok": False, "error": "Exam mode submission is not available yet."},
            status=400,
        )
    try:
        raw_answers = _json_body(request)
        validated, questions = _validated_answers(attempt, raw_answers)
    except AnswerPayloadError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    with transaction.atomic():
        locked = ListeningAttempt.objects.select_for_update().get(pk=attempt.pk)
        if locked.status == "submitted":
            return redirect("listening:result", pk=locked.pk)
        if locked.status != "in_progress":
            return JsonResponse(
                {"ok": False, "error": "This attempt cannot be submitted."},
                status=409,
            )
        _save_answer_values(locked, validated)
        _finish_attempt(locked)
    return redirect("listening:result", pk=attempt.pk)


@login_required
def attempt_result(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.status == "in_progress":
        return redirect("listening:attempt", pk=attempt.pk)
    return render(request, "listening/result_placeholder.html", {"attempt": attempt})
