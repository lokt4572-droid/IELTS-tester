"""Listening answer normalization and checking helpers."""

import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")
_MULTI_SEPARATOR = re.compile(r"[,;\s]+")
_LETTER_TYPES = {"mcq", "matching", "diagram_label"}


def normalize_answer(value):
    """Lowercase, normalize dashes/spacing, and remove surrounding punctuation."""
    text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    normalized = []
    for char in text:
        if unicodedata.category(char) == "Pd" or char == "\u2212":
            normalized.append("-")
        else:
            normalized.append(char)
    text = _WHITESPACE.sub(" ", "".join(normalized).casefold()).strip()

    start = 0
    end = len(text)
    while start < end and unicodedata.category(text[start]).startswith("P"):
        start += 1
    while end > start and unicodedata.category(text[end - 1]).startswith("P"):
        end -= 1
    return text[start:end].strip()


def accepted_answers(answer):
    """Return normalized alternatives separated by vertical bars."""
    return [
        normalized
        for part in str(answer if answer is not None else "").split("|")
        if (normalized := normalize_answer(part))
    ]


def check_answer(given, answer, qtype=None):
    """Check a single answer against alternatives; blank answers are always wrong."""
    normalized_given = normalize_answer(given)
    if not normalized_given:
        return False

    normalized_accepted = accepted_answers(answer)
    if qtype in _LETTER_TYPES:
        normalized_given = normalized_given.upper()
        normalized_accepted = [value.upper() for value in normalized_accepted]
    return normalized_given in normalized_accepted


def check_mcq_multi(given, answers):
    """Return one point per unique correct letter, independent of answer order."""
    given_letters = _letter_set(given)
    correct_letters = _letter_set(answers)
    return len(given_letters & correct_letters)


def _letter_set(values):
    if isinstance(values, str):
        candidates = _MULTI_SEPARATOR.split(values)
    else:
        try:
            candidates = list(values)
        except TypeError:
            candidates = [values]

    letters = set()
    for candidate in candidates:
        value = normalize_answer(candidate).upper()
        if len(value) == 1 and "A" <= value <= "Z":
            letters.add(value)
    return letters
