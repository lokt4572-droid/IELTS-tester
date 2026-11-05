"""Answer checking and band conversion. Pure Python so it is easy to test."""
import re
import unicodedata
from decimal import Decimal

_WS = re.compile(r"\s+")
_DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d)")
_STRIP = re.compile(r"[^\w\s'/%-]")


def normalize(value):
    s = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    s = s.casefold().replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    s = _DIGIT_COMMA.sub("", s)  # 1,000 -> 1000
    s = _STRIP.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def accepted_answers(answer):
    return [a for a in (normalize(x) for x in str(answer).split("|")) if a]


def check_answer(given, answer):
    """True if `given` matches any of the accepted alternatives (separated by '|')."""
    g = normalize(given)
    if not g:
        return False
    return g in accepted_answers(answer)


# (minimum raw score out of 40, band). Approximations of the commonly published
# conversion tables; real IELTS tables differ slightly between test versions.
ACADEMIC = [(39, 9.0), (37, 8.5), (35, 8.0), (33, 7.5), (30, 7.0), (27, 6.5), (23, 6.0),
            (19, 5.5), (15, 5.0), (13, 4.5), (10, 4.0), (8, 3.5), (6, 3.0), (4, 2.5),
            (3, 2.0), (2, 1.5), (1, 1.0), (0, 0.0)]
GENERAL = [(40, 9.0), (39, 8.5), (37, 8.0), (36, 7.5), (34, 7.0), (32, 6.5), (30, 6.0),
           (27, 5.5), (23, 5.0), (19, 4.5), (15, 4.0), (12, 3.5), (9, 3.0), (6, 2.5),
           (3, 2.0), (2, 1.5), (1, 1.0), (0, 0.0)]


def band_for(score, total, module="academic"):
    """Scale to 40 questions, then look up the band. Returns Decimal or None."""
    if not total:
        return None
    scaled = round(score / total * 40)
    table = GENERAL if module == "general" else ACADEMIC
    for minimum, band in table:
        if scaled >= minimum:
            return Decimal(str(band))
    return Decimal("0.0")
