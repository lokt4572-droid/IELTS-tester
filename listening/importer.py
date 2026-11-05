import os
from pathlib import Path

from django.core.files import File
from django.db import transaction

from .models import ListeningGroup, ListeningQuestion, ListeningSection, ListeningTest
from .schema import SchemaError, clean_payload


class AlreadyExists(Exception):
    pass


def _asset_path(base_dir, filename, where, required):
    if not filename:
        return None
    base = Path(base_dir).resolve()
    path = (base / filename).resolve()
    try:
        inside_base = os.path.commonpath((str(base), str(path))) == str(base)
    except ValueError:
        inside_base = False
    if Path(filename).is_absolute() or not inside_base:
        raise SchemaError([f"{where}: asset path must stay inside the JSON folder."])
    if not path.is_file():
        if required:
            raise SchemaError([f"{where}: required file '{filename}' was not found."])
        return None
    return path


def _attach_file(field, path):
    with path.open("rb") as stream:
        field.save(path.name, File(stream), save=True)


@transaction.atomic
def load_test(data, replace=False, publish=False, base_dir=None):
    """Validate and import a listening test and its local audio/image assets."""
    clean = clean_payload(data)
    asset_dir = Path(base_dir) if base_dir is not None else Path.cwd()
    warnings = list(clean["warnings"])
    resolved = []

    for section in clean["sections"]:
        section_where = f"section {section['number']}"
        audio_path = _asset_path(
            asset_dir, section["audio_file"], f"{section_where}.audio_file", required=True
        )
        section_image_path = _asset_path(
            asset_dir, section["image_file"], f"{section_where}.image_file", required=False
        )
        if section["image_file"] and section_image_path is None:
            warnings.append(
                f"{section_where}: image '{section['image_file']}' was not found; "
                "the section was imported without it."
            )
        group_paths = []
        for group_index, group in enumerate(section["groups"], 1):
            image_file = group["image_file"]
            image_path = _asset_path(
                asset_dir,
                image_file,
                f"{section_where} group {group_index}.image_file",
                required=False,
            )
            if image_file and image_path is None:
                warnings.append(
                    f"{section_where} group {group_index}: image '{image_file}' was not "
                    "found; the group was imported without it."
                )
            group_paths.append(image_path)
        resolved.append((audio_path, section_image_path, group_paths))

    existing = ListeningTest.objects.filter(slug=clean["slug"]).first()
    if existing:
        if not replace:
            raise AlreadyExists(
                f"A listening test with slug '{clean['slug']}' already exists (use --replace)."
            )
        existing.delete()

    test = ListeningTest.objects.create(
        title=clean["title"],
        slug=clean["slug"],
        description=clean["description"],
        duration_minutes=clean["duration_minutes"],
        review_seconds=clean["review_seconds"],
        source_name=clean["source_name"],
        source_url=clean["source_url"],
        license_note=clean["license_note"],
        is_published=publish,
    )
    test.import_warnings = warnings

    for section_index, section_data in enumerate(clean["sections"]):
        audio_path, section_image_path, group_image_paths = resolved[section_index]
        section = ListeningSection.objects.create(
            test=test,
            number=section_data["number"],
            title=section_data["title"],
            context=section_data["context"],
            audio="",
            audio_seconds=section_data["audio_seconds"],
            preview_seconds=section_data["preview_seconds"],
            check_seconds=section_data["check_seconds"],
            transcript=section_data["transcript"],
        )
        _attach_file(section.audio, audio_path)
        if section_image_path:
            _attach_file(section.image, section_image_path)

        for group_index, group_data in enumerate(section_data["groups"]):
            group = ListeningGroup.objects.create(
                section=section,
                order=group_index + 1,
                qtype=group_data["type"],
                instruction=group_data["instruction"],
                text=group_data["text"],
                options=group_data["options"],
                max_words=group_data["max_words"],
                choose=group_data["choose"],
                multi_question_numbers=group_data["multi_question_numbers"],
                multi_answers=group_data["multi_answers"],
            )
            group_image_path = group_image_paths[group_index]
            if group_image_path:
                _attach_file(group.image, group_image_path)
            ListeningQuestion.objects.bulk_create([
                ListeningQuestion(
                    test=test,
                    group=group,
                    number=question["number"],
                    text=question["text"],
                    answer=question["answer"],
                    options=question["options"],
                    explanation=question["explanation"],
                )
                for question in group_data["questions"]
            ])
    return test
