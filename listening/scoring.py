"""Listening raw-score to band conversion."""

from decimal import Decimal


_BAND_RANGES = (
    (39, 40, Decimal("9.0")),
    (37, 38, Decimal("8.5")),
    (35, 36, Decimal("8.0")),
    (32, 34, Decimal("7.5")),
    (30, 31, Decimal("7.0")),
    (26, 29, Decimal("6.5")),
    (23, 25, Decimal("6.0")),
    (18, 22, Decimal("5.5")),
    (16, 17, Decimal("5.0")),
    (13, 15, Decimal("4.5")),
    (10, 12, Decimal("4.0")),
    (8, 9, Decimal("3.5")),
    (6, 7, Decimal("3.0")),
    (4, 5, Decimal("2.5")),
)


def listening_band(raw_score, question_count):
    """Return the band for a 40-question test, otherwise ``None``."""
    if question_count != 40 or not isinstance(raw_score, int) or isinstance(raw_score, bool):
        return None
    if not 0 <= raw_score <= 40:
        return None
    for lower, upper, band in _BAND_RANGES:
        if lower <= raw_score <= upper:
            return band
    if raw_score == 3:
        return Decimal("2.0")
    if raw_score == 2:
        return Decimal("1.5")
    if raw_score == 1:
        return Decimal("1.0")
    return Decimal("0.0")
