from django.db import transaction

from .models import Passage, Question, QuestionGroup, ReadingTest
from .schema import clean_payload


class AlreadyExists(Exception):
    pass


@transaction.atomic
def load_test(data, replace=False, publish=False):
    """Validate `data` (see reading/schema.py) and store it. Returns the ReadingTest."""
    clean = clean_payload(data)
    existing = ReadingTest.objects.filter(slug=clean["slug"]).first()
    if existing:
        if not replace:
            raise AlreadyExists(f"A test with slug '{clean['slug']}' already exists (use replace).")
        existing.delete()
    test = ReadingTest.objects.create(
        title=clean["title"], slug=clean["slug"], module=clean["module"],
        description=clean["description"], duration_minutes=clean["duration_minutes"],
        source_name=clean["source_name"], source_url=clean["source_url"],
        license_note=clean["license_note"], translations=clean["translations"],
        is_published=publish,
    )
    test.import_warnings = clean["translation_warnings"]
    for pi, p in enumerate(clean["passages"], 1):
        passage = Passage.objects.create(test=test, order=pi, title=p["title"],
                                         subtitle=p["subtitle"], text=p["text"])
        for gi, g in enumerate(p["groups"], 1):
            group = QuestionGroup.objects.create(passage=passage, order=gi, qtype=g["type"],
                                                 instruction=g["instruction"], options=g["options"])
            Question.objects.bulk_create([
                Question(group=group, number=q["number"], text=q["text"], options=q["options"],
                         answer=q["answer"], explanation=q["explanation"])
                for q in g["questions"]
            ])
    return test
