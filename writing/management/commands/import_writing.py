import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from writing.importer import AlreadyExists, load_test
from writing.schema import SchemaError


class Command(BaseCommand):
    help = "Import writing tests from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--replace", action="store_true", help="Overwrite a test with the same slug.")
        parser.add_argument("--publish", action="store_true", help="Make imported tests visible to students.")

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.exists():
            raise CommandError(f"{path} does not exist.")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CommandError(f"{path.name}: invalid JSON ({exc})")

        try:
            test = load_test(data, replace=opts["replace"], publish=opts["publish"], basedir=path.parent)
        except SchemaError as exc:
            raise CommandError(f"{path.name}:\n  - " + "\n  - ".join(exc.errors))
        except AlreadyExists as exc:
            raise CommandError(str(exc))

        for warning in getattr(test, "import_warnings", []):
            self.stderr.write(self.style.WARNING(f"{path.name}: {warning}"))

        self.stdout.write(self.style.SUCCESS(
            f"Imported '{test.title}' ({len(test.tasks.all())} tasks, "
            f"{'published' if test.is_published else 'draft'})"
        ))
