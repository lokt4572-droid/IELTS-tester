"""Server-authoritative Listening exam phase schedule."""

from datetime import datetime, timedelta

from django.utils import timezone


def build_schedule(attempt):
    """Build absolute phase boundaries from the persisted exam start time."""
    if attempt.exam_started_at is None:
        return []

    phases = []
    cursor = attempt.exam_started_at
    sections = attempt.test.sections.order_by("number")
    for section in sections:
        for name, duration in (
            ("preview", section.preview_seconds),
            ("listen", section.audio_seconds),
            ("check", section.check_seconds),
        ):
            end = cursor + timedelta(seconds=duration)
            phases.append({
                "phase": name,
                "section_number": section.number,
                "start": cursor.isoformat(),
                "end": end.isoformat(),
                "duration_seconds": duration,
            })
            cursor = end
    end = cursor + timedelta(seconds=attempt.test.review_seconds)
    phases.append({
        "phase": "review",
        "section_number": None,
        "start": cursor.isoformat(),
        "end": end.isoformat(),
        "duration_seconds": attempt.test.review_seconds,
    })
    return phases


def phase_at(attempt, now=None):
    """Return the phase active at ``now``; intervals include start, exclude end."""
    now = now or timezone.now()
    if attempt.exam_started_at is None:
        return {
            "phase": "ready",
            "section_number": None,
            "phase_start": None,
            "phase_end": None,
            "remaining_seconds": None,
        }

    for phase in build_schedule(attempt):
        start = datetime.fromisoformat(phase["start"])
        end = datetime.fromisoformat(phase["end"])
        if start <= now < end:
            return {
                "phase": phase["phase"],
                "section_number": phase["section_number"],
                "phase_start": phase["start"],
                "phase_end": phase["end"],
                "remaining_seconds": max(0, int((end - now).total_seconds() + 0.999)),
            }
    return {
        "phase": "finished",
        "section_number": None,
        "phase_start": None,
        "phase_end": None,
        "remaining_seconds": 0,
    }
