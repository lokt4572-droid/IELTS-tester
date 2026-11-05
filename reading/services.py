from django.db import transaction
from django.utils import timezone

from .models import Attempt, Question
from .scoring import band_for, check_answer


def all_questions(test):
    return list(
        Question.objects.filter(group__passage__test=test)
        .select_related("group", "group__passage")
        .order_by("number")
    )


def collect_answers(post, questions):
    return {str(q.id): post.get(f"q_{q.id}", "").strip()[:200] for q in questions}


def evaluate(attempt):
    answers = attempt.answers or {}
    rows = []
    for q in all_questions(attempt.test):
        given = answers.get(str(q.id), "")
        rows.append({
            "question": q,
            "group": q.group,
            "passage": q.group.passage,
            "given": given,
            "correct": check_answer(given, q.answer),
            "expected": q.expected_display(),
        })
    return rows


def type_breakdown(rows):
    stats = {}
    for r in rows:
        label = r["group"].get_qtype_display()
        c, t = stats.get(label, (0, 0))
        stats[label] = (c + (1 if r["correct"] else 0), t + 1)
    return [{"label": k, "correct": c, "total": t, "percent": int(c / t * 100)} for k, (c, t) in stats.items()]


@transaction.atomic
def finish_attempt(attempt, answers=None, now=None):
    attempt = Attempt.objects.select_for_update().select_related("test").get(pk=attempt.pk)
    if attempt.finished_at:
        return attempt
    now = now or timezone.now()
    if answers is not None:
        attempt.answers = answers
    rows = evaluate(attempt)
    score = sum(1 for r in rows if r["correct"])
    attempt.score = score
    attempt.total = len(rows)
    attempt.band = band_for(score, len(rows), attempt.test.module)
    attempt.finished_at = now
    attempt.seconds_spent = max(0, int((now - attempt.started_at).total_seconds()))
    attempt.save()
    return attempt
