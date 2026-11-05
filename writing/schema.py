import re


class SchemaError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors[:5]))


def _s(value):
    return value.strip() if isinstance(value, str) else ""


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _as_int(value, default, *, minimum=None, maximum=None):
    try:
        val = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and val < minimum:
        return default
    if maximum is not None and val > maximum:
        return default
    return val


def _as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clean_payload(data):
    """Return a normalised copy of `data` or raise SchemaError listing problems."""
    errors = []
    warnings = []

    if not isinstance(data, dict):
        raise SchemaError(["Top level must be a JSON object."])

    allowed_top = {"title", "slug", "module", "duration_minutes", "description",
                   "source_name", "source_url", "license_note", "tasks"}
    for key in data.keys() - allowed_top:
        warnings.append(f"Unknown field '{key}' ignored.")

    title = _s(data.get("title"))
    if not title:
        errors.append("title is required.")

    slug = _s(data.get("slug")) or _slug(title)
    if not slug:
        errors.append("slug could not be created; give the test a title or slug.")

    module = _s(data.get("module")).lower() or "academic"
    if module not in {"academic", "general"}:
        errors.append("module must be 'academic' or 'general'.")

    duration = _as_int(data.get("duration_minutes", 60), 60, minimum=1, maximum=180)

    clean = {
        "title": title,
        "slug": slug,
        "module": module,
        "duration_minutes": duration,
        "description": _s(data.get("description")),
        "source_name": _s(data.get("source_name")),
        "source_url": _s(data.get("source_url")),
        "license_note": _s(data.get("license_note")),
        "warnings": warnings,
        "tasks": [],
    }

    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty list.")
        tasks = []

    seen_numbers = set()
    for index, raw_task in enumerate(tasks, 1):
        task_label = f"task {index}"
        if not isinstance(raw_task, dict):
            errors.append(f"{task_label}: must be an object.")
            continue

        allowed_task = {"task_number", "instructions", "prompt_text", "image_file",
                        "image_alt", "min_words", "suggested_minutes", "sample_answer",
                        "sample_answer_band"}
        for key in raw_task.keys() - allowed_task:
            warnings.append(f"{task_label}: unknown field '{key}' ignored.")

        task_number = _as_int(raw_task.get("task_number", index), index, minimum=1, maximum=2)
        if task_number not in {1, 2}:
            errors.append(f"{task_label}: task_number must be 1 or 2.")
            continue
        if task_number in seen_numbers:
            errors.append(f"{task_label}: task_number {task_number} is duplicated.")
        seen_numbers.add(task_number)

        instructions = _s(raw_task.get("instructions"))
        prompt_text = _s(raw_task.get("prompt_text"))
        if not prompt_text:
            errors.append(f"task {task_number}: prompt_text is required.")

        image_file = _s(raw_task.get("image_file")) or None
        image_alt = _s(raw_task.get("image_alt"))

        default_min = 150 if task_number == 1 else 250
        min_words = _as_int(raw_task.get("min_words", default_min), default_min, minimum=1)
        default_minutes = 20 if task_number == 1 else 40
        suggested_minutes = _as_int(raw_task.get("suggested_minutes", default_minutes), default_minutes, minimum=1)

        sample_answer = _s(raw_task.get("sample_answer"))
        sample_answer_band = _as_float(raw_task.get("sample_answer_band"))
        if sample_answer_band is not None and not 0 <= sample_answer_band <= 9:
            errors.append(f"task {task_number}: sample_answer_band must be between 0 and 9.")
            sample_answer_band = None

        clean["tasks"].append({
            "task_number": task_number,
            "instructions": instructions,
            "prompt_text": prompt_text,
            "image_file": image_file,
            "image_alt": image_alt,
            "min_words": min_words,
            "suggested_minutes": suggested_minutes,
            "sample_answer": sample_answer,
            "sample_answer_band": sample_answer_band,
        })

    if len(clean["tasks"]) != 2:
        errors.append("Each test must contain exactly Task 1 and Task 2.")
    else:
        task_numbers = sorted(t["task_number"] for t in clean["tasks"])
        if task_numbers != [1, 2]:
            errors.append(f"Task numbers must be exactly [1, 2]; found {task_numbers}.")

    if errors:
        raise SchemaError(errors)

    return clean
