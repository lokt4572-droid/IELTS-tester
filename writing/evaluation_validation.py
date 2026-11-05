"""Validation and normalization for structured AI Writing assessments."""

from decimal import Decimal, InvalidOperation

from .scoring import task_band

VALIDATION_VERSION = "2"

CRITERIA = (
    "task_achievement_or_response",
    "coherence_and_cohesion",
    "lexical_resource",
    "grammatical_range_and_accuracy",
)


class EvaluationValidationError(ValueError):
    """Raised when model output does not match the supported evaluation schema."""


def _band(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationValidationError(f"{field} must be a numeric band.")
    try:
        band = Decimal(str(value))
    except InvalidOperation:
        raise EvaluationValidationError(f"{field} must be a valid numeric band.")
    if not band.is_finite() or not 0 <= band <= 9 or band % Decimal("0.5"):
        raise EvaluationValidationError(f"{field} must be between 0 and 9 in half-band steps.")
    return float(band)


def _text(value, field, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise EvaluationValidationError(f"{field} must be a non-empty string of at most {maximum} characters.")
    return value.strip()


def _list_of_text(data, field, minimum=1):
    if not isinstance(data, list) or not minimum <= len(data) <= 8:
        if minimum == 0:
            raise EvaluationValidationError(f"{field} must contain between zero and eight items.")
        raise EvaluationValidationError(f"{field} must contain between one and eight items.")
    return [_text(value, f"{field} item", maximum=1000) for value in data]


def _canonical_text_with_spans(value, ignore_whitespace=False):
    canonical = []
    starts = []
    ends = []
    in_whitespace = False
    for index, character in enumerate(value):
        if character.isspace():
            if ignore_whitespace:
                continue
            if in_whitespace:
                ends[-1] = index + 1
                continue
            character = " "
            in_whitespace = True
        else:
            in_whitespace = False

        if character in {"‘", "’", "‛", "＇"}:
            character = "'"
        elif character in {"“", "”", "„", "‟", "＂"}:
            character = '"'
        elif character in {"–", "—"}:
            character = "-"

        folded = character.casefold()
        for folded_character in folded:
            canonical.append(folded_character)
            starts.append(index)
            ends.append(index + 1)

    return "".join(canonical), starts, ends


def _verified_quote(quote, learner_response):
    if not isinstance(quote, str) or not quote.strip():
        return None

    response_text, response_starts, response_ends = _canonical_text_with_spans(
        learner_response
    )
    quote_text, _, _ = _canonical_text_with_spans(quote.strip())
    match_start = response_text.find(quote_text)
    match_end = match_start + len(quote_text) if match_start >= 0 else -1

    if match_start < 0:
        response_text, response_starts, response_ends = _canonical_text_with_spans(
            learner_response,
            ignore_whitespace=True,
        )
        quote_text, _, _ = _canonical_text_with_spans(
            quote.strip(),
            ignore_whitespace=True,
        )
        match_start = response_text.find(quote_text)
        match_end = match_start + len(quote_text) if match_start >= 0 else -1

    if match_start < 0 or match_end <= match_start:
        return None

    original_start = response_starts[match_start]
    original_end = response_ends[match_end - 1]
    return learner_response[original_start:original_end]


def validate_evaluation(data, learner_response):
    if not isinstance(data, dict):
        raise EvaluationValidationError("Evaluation output must be a JSON object.")
    if set(data) != {"criteria", "overall"}:
        raise EvaluationValidationError("Evaluation output has an unexpected JSON structure.")

    criteria = data["criteria"]
    if not isinstance(criteria, dict) or set(criteria) != set(CRITERIA):
        raise EvaluationValidationError("Evaluation must include all four IELTS criteria.")

    normalized_criteria = {}
    bands = []
    for criterion in CRITERIA:
        entry = criteria[criterion]
        if not isinstance(entry, dict) or set(entry) != {"band", "comment", "evidence"}:
            raise EvaluationValidationError(f"{criterion} must include band, comment, and evidence.")
        band = _band(entry["band"], f"{criterion}.band")
        evidence = entry["evidence"]
        if not isinstance(evidence, list) or len(evidence) > 8:
            raise EvaluationValidationError(f"{criterion}.evidence must be a list of at most eight quotes.")
        normalized_criteria[criterion] = {
            "band": band,
            "comment": _text(entry["comment"], f"{criterion}.comment"),
            "evidence": [
                _text(verified_quote, f"{criterion}.evidence item", maximum=1000)
                for quote in evidence
                if (verified_quote := _verified_quote(quote, learner_response)) is not None
            ],
        }
        bands.append(band)

    estimate = task_band(*bands)

    overall = data["overall"]
    if not isinstance(overall, dict) or set(overall) != {
        "strengths", "weaknesses", "corrections", "next_steps", "summary"
    }:
        raise EvaluationValidationError("overall must include strengths, weaknesses, corrections, next_steps, and summary.")

    corrections = overall["corrections"]
    if not isinstance(corrections, list):
        raise EvaluationValidationError("corrections must be a list.")
    if len(corrections) > 5:
        raise EvaluationValidationError("corrections may contain at most five items.")
    normalized_corrections = []
    for correction in corrections:
        if not isinstance(correction, dict) or set(correction) != {"original", "improved", "reason"}:
            raise EvaluationValidationError("Each correction must include original, improved, and reason.")
        verified_original = _verified_quote(correction["original"], learner_response)
        if verified_original is None:
            continue
        original = _text(verified_original, "correction.original", maximum=1000)
        improved = _text(correction["improved"], "correction.improved", maximum=1000)
        reason = _text(correction["reason"], "correction.reason", maximum=1000)
        normalized_corrections.append({
            "original": original,
            "improved": improved,
            "reason": reason,
        })

    return {
        "criteria": normalized_criteria,
        "task_band_estimate": estimate,
        "overall": {
            "strengths": _list_of_text(overall["strengths"], "strengths", minimum=0),
            "weaknesses": _list_of_text(overall["weaknesses"], "weaknesses", minimum=0),
            "corrections": normalized_corrections,
            "next_steps": _list_of_text(overall["next_steps"], "next_steps"),
            "summary": _text(overall["summary"], "summary"),
        },
    }
