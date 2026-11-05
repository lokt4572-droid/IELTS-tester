import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from listening.importer import AlreadyExists, load_test
from listening.schema import SchemaError


class Command(BaseCommand):
    help = "Import a listening test from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Overwrite a test with the same slug.",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Make the imported test visible to students.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_file():
            raise CommandError(f"{path} is not a file.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"{path.name}: could not read valid JSON ({exc})") from exc

        try:
            test = load_test(
                data,
                replace=options["replace"],
                publish=options["publish"],
                base_dir=path.resolve().parent,
            )
        except SchemaError as exc:
            raise CommandError(f"{path.name}:\n  - " + "\n  - ".join(exc.errors)) from exc
        except AlreadyExists as exc:
            raise CommandError(str(exc)) from exc

        for warning in test.import_warnings:
            self.stderr.write(self.style.WARNING(f"{path.name}: {warning}"))
        self.stdout.write(self.style.SUCCESS(
            f"Imported '{test.title}' ({test.question_count()} questions, "
            f"{'published' if test.is_published else 'draft'})."
        ))
