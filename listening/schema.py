"""Validation of the JSON format used to import listening tests."""

import re


QTYPES = {"mcq", "mcq_multi", "matching", "completion", "short", "diagram_label"}


class SchemaError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors[:5]))


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _integer(value, default, label, errors, minimum=0, maximum=None):
    try:
        number = int(value)
        if isinstance(value, bool):
            raise ValueError
        if number < minimum or (maximum is not None and number > maximum):
            raise ValueError
        return number
    except (TypeError, ValueError):
        high = f" and no more than {maximum}" if maximum is not None else ""
        errors.append(f"{label} must be an integer of at least {minimum}{high}.")
        return default


def _clean_options(raw, where, errors, required=False):
    if raw in (None, []):
        if required:
            errors.append(f"{where}: needs at least two options.")
        return []
    if not isinstance(raw, list):
        errors.append(f"{where}: options must be a list.")
        return []

    cleaned = []
    for index, option in enumerate(raw, 1):
        if isinstance(option, dict):
            key = _text(option.get("key")).upper()
            text = _text(option.get("text"))
            if re.fullmatch(r"[A-Z]", key) and text:
                cleaned.append({"key": key, "text": text})
                continue
        errors.append(f"{where}: option {index} needs a single-letter key and non-empty text.")

    keys = [option["key"] for option in cleaned]
    if len(keys) != len(set(keys)):
        errors.append(f"{where}: option keys must be unique.")
    if required and len(cleaned) < 2:
        errors.append(f"{where}: needs at least two options.")
    return cleaned


def _validate_answer_keys(answers, options, where, errors):
    keys = {option["key"] for option in options}
    for answer in answers:
        if answer.upper() not in keys:
            errors.append(f"{where}: answer '{answer}' is not one of the option keys.")


def _unknown_fields(data, allowed, where, warnings):
    for key in sorted(set(data) - allowed):
        warnings.append(f"{where}: unknown field '{key}' was ignored.")


def clean_payload(data):
    """Return a normalized payload or raise SchemaError with all detected issues."""
    if not isinstance(data, dict):
        raise SchemaError(["Top level must be a JSON object."])

    errors = []
    warnings = []
    _unknown_fields(
        data,
        {
            "title", "slug", "description", "duration_minutes", "review_seconds",
            "source_name", "source_url", "license_note", "sections",
        },
        "test",
        warnings,
    )

    title = _text(data.get("title"))
    source_name = _text(data.get("source_name"))
    license_note = _text(data.get("license_note"))
    if not title:
        errors.append("title is required.")
    if not source_name:
        errors.append("source_name is required.")
    if not license_note:
        errors.append("license_note is required.")

    slug = _text(data.get("slug")) or _slug(title)
    if not slug:
        errors.append("slug could not be created; provide a title or slug.")

    duration = _integer(data.get("duration_minutes", 30), 30, "duration_minutes", errors, 1)
    review_seconds = _integer(
        data.get("review_seconds", 120), 120, "review_seconds", errors, 0
    )
    sections_data = data.get("sections")
    if not isinstance(sections_data, list) or len(sections_data) != 4:
        errors.append("sections must contain exactly four section objects.")
        sections_data = sections_data if isinstance(sections_data, list) else []

    clean_sections = []
    question_numbers = []
    seen_section_numbers = set()
    for section_index, section in enumerate(sections_data, 1):
        where = f"section {section_index}"
        if not isinstance(section, dict):
            errors.append(f"{where}: must be an object.")
            continue
        _unknown_fields(
            section,
            {
                "number", "title", "context", "audio_file", "audio_seconds",
                "preview_seconds", "check_seconds", "transcript", "image_file", "groups",
            },
            where,
            warnings,
        )

        number = _integer(section.get("number"), section_index, f"{where}.number", errors, 1, 4)
        if number in seen_section_numbers:
            errors.append(f"{where}: section number {number} is duplicated.")
        seen_section_numbers.add(number)
        if number != section_index:
            errors.append("sections must be numbered 1, 2, 3, 4 in order.")

        title_value = _text(section.get("title"))
        audio_file = _text(section.get("audio_file"))
        if not title_value:
            errors.append(f"{where}: title is required.")
        if not audio_file:
            errors.append(f"{where}: audio_file is required.")

        audio_seconds = _integer(
            section.get("audio_seconds"), 0, f"{where}.audio_seconds", errors, 1
        )
        preview_seconds = _integer(
            section.get("preview_seconds", 30), 30, f"{where}.preview_seconds", errors
        )
        check_seconds = _integer(
            section.get("check_seconds", 30), 30, f"{where}.check_seconds", errors
        )

        section_clean = {
            "number": number,
            "title": title_value,
            "context": _text(section.get("context")),
            "audio_file": audio_file,
            "audio_seconds": audio_seconds,
            "preview_seconds": preview_seconds,
            "check_seconds": check_seconds,
            "transcript": _text(section.get("transcript")),
            "image_file": _text(section.get("image_file")),
            "groups": [],
        }
        groups = section.get("groups")
        if not isinstance(groups, list) or not groups:
            errors.append(f"{where}: groups must be a non-empty list.")
            groups = []

        for group_index, group in enumerate(groups, 1):
            group_where = f"{where} group {group_index}"
            if not isinstance(group, dict):
                errors.append(f"{group_where}: must be an object.")
                continue
            qtype = _text(group.get("type")).lower()
            if qtype not in QTYPES:
                errors.append(f"{group_where}: type must be one of {sorted(QTYPES)}.")
                continue

            if qtype == "mcq_multi":
                allowed_group_fields = {
                    "type", "instruction", "choose", "numbers", "text", "options",
                    "answers", "explanation",
                }
            else:
                allowed_group_fields = {
                    "type", "instruction", "max_words", "options", "image_file", "questions",
                }
            _unknown_fields(group, allowed_group_fields, group_where, warnings)
            required_options = qtype in {"matching", "mcq_multi", "diagram_label"}
            options = _clean_options(
                group.get("options"),
                group_where,
                errors,
                required=required_options,
            )
            group_clean = {
                "type": qtype,
                "instruction": _text(group.get("instruction")),
                "options": options,
                "max_words": None,
                "choose": None,
                "text": "",
                "image_file": _text(group.get("image_file")),
                "multi_question_numbers": [],
                "multi_answers": [],
                "multi_explanation": "",
                "questions": [],
            }
            if qtype == "diagram_label" and not group_clean["image_file"]:
                errors.append(f"{group_where}: image_file is required for diagram_label.")

            if qtype == "mcq_multi":
                choose = _integer(group.get("choose"), 0, f"{group_where}.choose", errors, 2, 3)
                raw_numbers = group.get("numbers")
                raw_answers = group.get("answers")
                numbers = []
                answers = []
                if not isinstance(raw_numbers, list):
                    errors.append(f"{group_where}: numbers must be a list.")
                else:
                    for value in raw_numbers:
                        numbers.append(
                            _integer(value, 0, f"{group_where}.numbers item", errors, 1, 40)
                        )
                if not isinstance(raw_answers, list):
                    errors.append(f"{group_where}: answers must be a list.")
                else:
                    answers = [_text(value).upper() for value in raw_answers]
                if len(numbers) != choose:
                    errors.append(f"{group_where}: numbers must contain exactly {choose} entries.")
                if len(answers) != choose:
                    errors.append(f"{group_where}: answers must contain exactly {choose} letters.")
                if len(numbers) != len(set(numbers)):
                    errors.append(f"{group_where}: numbers must be unique.")
                if len(answers) != len(set(answers)):
                    errors.append(f"{group_where}: answers must be unique letters.")
                _validate_answer_keys(answers, options, group_where, errors)
                prompt = _text(group.get("text"))
                if not prompt:
                    errors.append(f"{group_where}: text is required.")
                explanation = _text(group.get("explanation"))
                group_clean.update({
                    "choose": choose,
                    "text": prompt,
                    "multi_question_numbers": numbers,
                    "multi_answers": answers,
                    "multi_explanation": explanation,
                    "questions": [
                        {
                            "number": question_number,
                            "text": prompt,
                            "answer": answer,
                            "options": [],
                            "explanation": explanation,
                        }
                        for question_number, answer in zip(numbers, answers)
                    ],
                })
                question_numbers.extend(numbers)
            else:
                max_words = None
                if "max_words" in group:
                    max_words = _integer(
                        group["max_words"], 0, f"{group_where}.max_words", errors, 1
                    )
                group_clean["max_words"] = max_words
                raw_questions = group.get("questions")
                if not isinstance(raw_questions, list) or not raw_questions:
                    errors.append(f"{group_where}: questions must be a non-empty list.")
                    raw_questions = []
                for question_index, question in enumerate(raw_questions, 1):
                    question_where = f"{group_where} question {question_index}"
                    if not isinstance(question, dict):
                        errors.append(f"{question_where}: must be an object.")
                        continue
                    _unknown_fields(
                        question,
                        {"number", "text", "options", "answer", "explanation"},
                        question_where,
                        warnings,
                    )
                    question_number = _integer(
                        question.get("number"),
                        0,
                        f"{question_where}.number",
                        errors,
                        1,
                        40,
                    )
                    question_numbers.append(question_number)
                    text = _text(question.get("text"))
                    answer = _text(question.get("answer"))
                    if not text:
                        errors.append(f"{question_where}: text is required.")
                    if not answer:
                        errors.append(f"{question_where}: answer is required.")
                    if qtype == "completion" and "____" not in text:
                        errors.append(f"{question_where}: completion text must contain ____.")

                    question_options = []
                    if qtype == "mcq":
                        question_options = _clean_options(
                            question.get("options"),
                            question_where,
                            errors,
                            required=True,
                        )
                        _validate_answer_keys(
                            [part.strip().upper() for part in answer.split("|") if part.strip()],
                            question_options,
                            question_where,
                            errors,
                        )
                    elif qtype in {"matching", "diagram_label"}:
                        _validate_answer_keys(
                            [part.strip().upper() for part in answer.split("|") if part.strip()],
                            options,
                            question_where,
                            errors,
                        )
                    group_clean["questions"].append({
                        "number": question_number,
                        "text": text,
                        "answer": answer,
                        "options": question_options,
                        "explanation": _text(question.get("explanation")),
                    })

            section_clean["groups"].append(group_clean)
        clean_sections.append(section_clean)

    if sorted(seen_section_numbers) != [1, 2, 3, 4]:
        errors.append("section numbers must contain each number from 1 through 4.")
    if question_numbers != list(range(1, 41)):
        errors.append(
            "question numbers must run 1 through 40 in order across the whole test "
            f"(found {question_numbers[:12]}{'...' if len(question_numbers) > 12 else ''})."
        )

    if errors:
        raise SchemaError(errors)

    return {
        "title": title,
        "slug": slug,
        "description": _text(data.get("description")),
        "duration_minutes": duration,
        "review_seconds": review_seconds,
        "source_name": source_name,
        "source_url": _text(data.get("source_url")),
        "license_note": license_note,
        "sections": clean_sections,
        "warnings": warnings,
    }
