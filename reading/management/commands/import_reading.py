import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from reading.importer import AlreadyExists, load_test
from reading.schema import SchemaError


class Command(BaseCommand):
    help = "Import reading tests from a JSON file (or every .json file in a folder)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--replace", action="store_true", help="Overwrite a test with the same slug.")
        parser.add_argument("--publish", action="store_true", help="Make imported tests visible to students.")

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.exists():
            raise CommandError(f"{path} does not exist.")
        files = sorted(path.glob("*.json")) if path.is_dir() else [path]
        if not files:
            raise CommandError("No .json files found.")
        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise CommandError(f"{f.name}: invalid JSON ({exc})")
            for item in data if isinstance(data, list) else [data]:
                try:
                    test = load_test(item, replace=opts["replace"], publish=opts["publish"])
                except SchemaError as exc:
                    raise CommandError(f"{f.name}:\n  - " + "\n  - ".join(exc.errors))
                except AlreadyExists as exc:
                    raise CommandError(str(exc))
                for warning in test.import_warnings:
                    self.stderr.write(self.style.WARNING(f"{f.name}: {warning}"))
                self.stdout.write(self.style.SUCCESS(
                    f"Imported '{test.title}' ({test.question_count()} questions, "
                    f"{'published' if test.is_published else 'draft'})"))
