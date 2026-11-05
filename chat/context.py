from reading.models import Attempt, Question


def build_question_context(user, attempt_id, question_id):
    """Context for 'explain this question'. Only for the user's own finished attempts."""
    try:
        attempt_id, question_id = int(attempt_id), int(question_id)
    except (TypeError, ValueError):
        return None
    attempt = (Attempt.objects.filter(pk=attempt_id, user=user, finished_at__isnull=False)
               .select_related("test").first())
    if not attempt:
        return None
    q = (Question.objects.filter(pk=question_id, group__passage__test=attempt.test)
         .select_related("group", "group__passage").first())
    if not q:
        return None
    passage = q.group.passage
    given = (attempt.answers or {}).get(str(q.id), "") or "(left blank)"
    lines = [
        "[Context from the student's IELTS Reading practice]",
        f"Passage: {passage.title}",
        passage.text[:7000],
        "",
        f"Question {q.number} ({q.group.get_qtype_display()}). Instruction: {q.group.instruction}",
        q.text,
    ]
    if q.group.qtype == "mcq":
        lines += [f"{o['key']}. {o['text']}" for o in q.options]
    lines += [f"Student's answer: {given}", f"Correct answer: {q.expected_display()}"]
    return {"label": f"Question {q.number} from \u201c{passage.title}\u201d", "text": "\n".join(lines)}
