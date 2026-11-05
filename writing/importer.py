import json
from pathlib import Path

from django.core.files import File
from django.db import transaction

from .models import WritingTask, WritingTest
from .schema import SchemaError, clean_payload


class AlreadyExists(Exception):
    pass


@transaction.atomic
def load_test(data, replace=False, publish=False, basedir=None):
    """Validate `data` and store it. Returns the WritingTest."""
    clean = clean_payload(data)
    existing = WritingTest.objects.filter(slug=clean["slug"]).first()
    if existing:
        if not replace:
            raise AlreadyExists(f"A test with slug '{clean['slug']}' already exists (use replace).")
        existing.delete()

    test = WritingTest.objects.create(
        title=clean["title"],
        slug=clean["slug"],
        module=clean["module"],
        duration_minutes=clean["duration_minutes"],
        description=clean["description"],
        source_name=clean["source_name"],
        source_url=clean["source_url"],
        license_note=clean["license_note"],
        is_published=publish,
    )
    test.import_warnings = list(clean["warnings"])

    ordered_tasks = sorted(clean["tasks"], key=lambda t: t["task_number"])
    for task_data in ordered_tasks:
        task = WritingTask.objects.create(
            test=test,
            task_number=task_data["task_number"],
            instructions=task_data["instructions"],
            prompt_text=task_data["prompt_text"],
            image_alt=task_data["image_alt"],
            min_words=task_data["min_words"],
            suggested_minutes=task_data["suggested_minutes"],
            sample_answer=task_data["sample_answer"],
            sample_answer_band=task_data["sample_answer_band"],
        )

        image_file = task_data.get("image_file")
        if not image_file:
            continue

        search_candidates = []
        if basedir:
            search_candidates.append(Path(basedir) / image_file)
        search_candidates.append(Path(image_file))

        resolved = None
        for candidate in search_candidates:
            if candidate.exists():
                resolved = candidate
                break

        if not resolved:
            test.import_warnings.append(
                f"Task {task.task_number}: image file '{image_file}' not found; task imported without an image."
            )
            continue

        with resolved.open("rb") as handle:
            task.image.save(resolved.name, File(handle), save=True)

    return test
