from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Attempt, ReadingTest
from .services import all_questions, collect_answers, evaluate, finish_attempt, type_breakdown


def test_list(request):
    tests = (
        ReadingTest.objects.filter(is_published=True)
        .annotate(n_questions=Count("passages__groups__questions", distinct=True),
                  n_passages=Count("passages", distinct=True))
    )
    return render(request, "reading/test_list.html", {"tests": tests})


def test_detail(request, slug):
    test = get_object_or_404(ReadingTest, slug=slug, is_published=True)
    history = []
    if request.user.is_authenticated:
        history = list(Attempt.objects.filter(user=request.user, test=test, finished_at__isnull=False)[:5])
    return render(request, "reading/test_detail.html", {
        "test": test, "history": history, "n_questions": test.question_count(),
        "passages": test.passages.all(),
    })


@login_required
@require_POST
def start_attempt(request, slug):
    test = get_object_or_404(ReadingTest, slug=slug, is_published=True)
    open_attempt = (Attempt.objects.filter(user=request.user, test=test, finished_at__isnull=True)
                    .order_by("-started_at").first())
    if open_attempt:
        if not open_attempt.is_expired():
            return redirect("reading:attempt", pk=open_attempt.pk)
        finish_attempt(open_attempt)  # time ran out last time: score what was saved
    attempt = Attempt.objects.create(user=request.user, test=test)
    return redirect("reading:attempt", pk=attempt.pk)


def _own_attempt(request, pk):
    return get_object_or_404(Attempt.objects.select_related("test"), pk=pk, user=request.user)


@login_required
def attempt_page(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.finished_at:
        return redirect("reading:result", pk=attempt.pk)
    if attempt.is_expired():
        finish_attempt(attempt)
        return redirect("reading:result", pk=attempt.pk)
    passages = list(attempt.test.passages.prefetch_related("groups__questions"))
    saved = attempt.answers or {}
    total = 0
    for passage in passages:
        for group in passage.groups.all():
            for q in group.questions.all():
                q.saved = saved.get(str(q.id), "")
                total += 1
    return render(request, "reading/attempt.html", {
        "attempt": attempt, "test": attempt.test, "passages": passages,
        "seconds_left": attempt.seconds_left(), "total": total,
    })


@login_required
@require_POST
def attempt_save(request, pk):
    attempt = _own_attempt(request, pk)
    if attempt.finished_at:
        return JsonResponse({"ok": False, "finished": True}, status=409)
    answers = collect_answers(request.POST, all_questions(attempt.test))
    attempt.answers = answers
    attempt.save(update_fields=["answers"])
    return JsonResponse({"ok": True, "answered": sum(1 for v in answers.values() if v)})


@login_required
@require_POST
def attempt_submit(request, pk):
    attempt = _own_attempt(request, pk)
    if not attempt.finished_at:
        answers = collect_answers(request.POST, all_questions(attempt.test))
        finish_attempt(attempt, answers)
    return redirect("reading:result", pk=attempt.pk)


@login_required
def attempt_result(request, pk):
    attempt = _own_attempt(request, pk)
    if not attempt.finished_at:
        return redirect("reading:attempt", pk=attempt.pk)
    rows = evaluate(attempt)
    minutes, seconds = divmod(attempt.seconds_spent, 60)
    return render(request, "reading/result.html", {
        "attempt": attempt, "test": attempt.test, "rows": rows,
        "breakdown": type_breakdown(rows), "time_text": f"{minutes}m {seconds:02d}s",
        "percent": int(attempt.score / attempt.total * 100) if attempt.total else 0,
    })
