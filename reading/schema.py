"""Validation of the JSON format used to import reading tests. Pure Python."""
import re

QTYPES = {"tfng", "ynng", "mcq", "matching", "completion", "short"}
_TFNG = {"TRUE": "TRUE", "T": "TRUE", "FALSE": "FALSE", "F": "FALSE",
         "NOT GIVEN": "NOT GIVEN", "NG": "NOT GIVEN", "NOTGIVEN": "NOT GIVEN"}
_YNNG = {"YES": "YES", "Y": "YES", "NO": "NO", "N": "NO",
         "NOT GIVEN": "NOT GIVEN", "NG": "NOT GIVEN", "NOTGIVEN": "NOT GIVEN"}


class SchemaError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors[:5]))


def _s(value):
    return value.strip() if isinstance(value, str) else ""


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _letters(i):
    return chr(ord("A") + i) if i < 26 else str(i + 1)


def _clean_options(raw, where, errors, required):
    if raw in (None, []):
        if required:
            errors.append(f"{where}: needs at least 2 options.")
        return []
    if not isinstance(raw, list):
        errors.append(f"{where}: options must be a list.")
        return []
    out = []
    for i, item in enumerate(raw):
        if isinstance(item, str) and _s(item):
            out.append({"key": _letters(i), "text": _s(item)})
        elif isinstance(item, dict) and _s(item.get("key")) and _s(item.get("text")):
            out.append({"key": _s(item["key"]), "text": _s(item["text"])})
        else:
            errors.append(f"{where}: option {i + 1} needs 'key' and 'text'.")
    if required and len(out) < 2:
        errors.append(f"{where}: needs at least 2 options.")
    keys = [o["key"].casefold() for o in out]
    if len(keys) != len(set(keys)):
        errors.append(f"{where}: option keys must be unique.")
    return out


def _match_key(options, answer):
    for o in options:
        if o["key"].casefold() == answer.casefold():
            return o["key"]
    return None


def _clean_translations(data):
    if "translations" not in data:
        return {}, []
    translations = data["translations"]
    if not isinstance(translations, dict):
        return {}, ["translations must be an object; translations were skipped."]
    for language, translation in translations.items():
        if not isinstance(translation, dict):
            return {}, [
                f"translations.{language} must be an object; translations were skipped."
            ]
        if not isinstance(translation.get("words"), dict):
            return {}, [
                f"translations.{language}.words must be an object; translations were skipped."
            ]
    return translations, []


def clean_payload(data):
    """Return a normalised copy of `data` or raise SchemaError listing every problem."""
    errors = []
    if not isinstance(data, dict):
        raise SchemaError(["Top level must be a JSON object."])

    title = _s(data.get("title"))
    if not title:
        errors.append("title is required.")
    source_name = _s(data.get("source_name"))
    license_note = _s(data.get("license_note"))
    translations, translation_warnings = _clean_translations(data)
    if not source_name:
        errors.append("source_name is required (where the test comes from).")
    if not license_note:
        errors.append("license_note is required (why you may use this text).")

    module = _s(data.get("module")).lower() or "academic"
    if module not in {"academic", "general"}:
        errors.append("module must be 'academic' or 'general'.")
    try:
        duration = int(data.get("duration_minutes", 60))
        if not 1 <= duration <= 180:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("duration_minutes must be a number from 1 to 180.")
        duration = 60

    clean = {
        "title": title,
        "slug": _s(data.get("slug")) or _slug(title),
        "module": module,
        "duration_minutes": duration,
        "description": _s(data.get("description")),
        "source_name": source_name,
        "source_url": _s(data.get("source_url")),
        "license_note": license_note,
        "translations": translations,
        "translation_warnings": translation_warnings,
        "passages": [],
    }
    if not clean["slug"]:
        errors.append("slug could not be created; give the test a title or slug.")

    passages = data.get("passages")
    if not isinstance(passages, list) or not passages:
        errors.append("passages must be a non-empty list.")
        passages = []

    numbers = []
    for pi, p in enumerate(passages, 1):
        pw = f"passage {pi}"
        if not isinstance(p, dict):
            errors.append(f"{pw}: must be an object.")
            continue
        cp = {"title": _s(p.get("title")), "subtitle": _s(p.get("subtitle")),
              "text": _s(p.get("text")), "groups": []}
        if not cp["title"]:
            errors.append(f"{pw}: title is required.")
        if not cp["text"]:
            errors.append(f"{pw}: text is required.")
        groups = p.get("groups")
        if not isinstance(groups, list) or not groups:
            errors.append(f"{pw}: groups must be a non-empty list.")
            groups = []
        for gi, g in enumerate(groups, 1):
            gw = f"{pw} group {gi}"
            if not isinstance(g, dict):
                errors.append(f"{gw}: must be an object.")
                continue
            qtype = _s(g.get("type")).lower()
            if qtype not in QTYPES:
                errors.append(f"{gw}: type must be one of {sorted(QTYPES)}.")
                continue
            cg = {"type": qtype, "instruction": _s(g.get("instruction")),
                  "options": _clean_options(g.get("options"), gw, errors, qtype == "matching"),
                  "questions": []}
            qs = g.get("questions")
            if not isinstance(qs, list) or not qs:
                errors.append(f"{gw}: questions must be a non-empty list.")
                qs = []
            for qi, q in enumerate(qs, 1):
                qw = f"{gw} question {qi}"
                if not isinstance(q, dict):
                    errors.append(f"{qw}: must be an object.")
                    continue
                try:
                    number = int(q.get("number"))
                except (TypeError, ValueError):
                    errors.append(f"{qw}: number must be an integer.")
                    continue
                qw = f"{gw} question {number}"
                text = _s(q.get("text"))
                answer = _s(q.get("answer"))
                if not text:
                    errors.append(f"{qw}: text is required.")
                if not answer:
                    errors.append(f"{qw}: answer is required.")
                qopts = []
                if qtype == "tfng":
                    answer = _TFNG.get(answer.upper(), "")
                    if not answer:
                        errors.append(f"{qw}: answer must be TRUE, FALSE or NOT GIVEN.")
                elif qtype == "ynng":
                    answer = _YNNG.get(answer.upper(), "")
                    if not answer:
                        errors.append(f"{qw}: answer must be YES, NO or NOT GIVEN.")
                elif qtype == "mcq":
                    qopts = _clean_options(q.get("options"), qw, errors, True)
                    if qopts and answer:
                        key = _match_key(qopts, answer)
                        if key is None:
                            errors.append(f"{qw}: answer '{answer}' is not one of the option keys.")
                        else:
                            answer = key
                elif qtype == "matching":
                    if cg["options"] and answer:
                        key = _match_key(cg["options"], answer)
                        if key is None:
                            errors.append(f"{qw}: answer '{answer}' is not in the group's options.")
                        else:
                            answer = key
                numbers.append(number)
                cg["questions"].append({"number": number, "text": text, "answer": answer,
                                        "options": qopts, "explanation": _s(q.get("explanation"))})
            cp["groups"].append(cg)
        clean["passages"].append(cp)

    if numbers and numbers != list(range(1, len(numbers) + 1)):
        errors.append("question numbers must run 1, 2, 3 ... in order across the whole test "
                      f"(found {numbers[:12]}{'...' if len(numbers) > 12 else ''}).")
    if errors:
        raise SchemaError(errors)
    return clean
