import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from listening.importer import AlreadyExists, load_test
from listening.models import ListeningQuestion, ListeningSection, ListeningTest
from listening.schema import SchemaError
from listening.tests.test_schema import sample_payload


class ListeningImporterTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.temp_dir.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.base_dir = Path(self.temp_dir.name) / "json-assets"
        self.base_dir.mkdir()
        for section_number in range(1, 5):
            (self.base_dir / f"section-{section_number}.mp3").write_bytes(b"audio")

    def test_import_saves_test_sections_questions_and_audio(self):
        test = load_test(sample_payload(), base_dir=self.base_dir, publish=True)
        self.assertTrue(test.is_published)
        self.assertEqual(test.sections.count(), 4)
        self.assertEqual(test.question_count(), 40)
        self.assertEqual(ListeningQuestion.objects.filter(test=test).count(), 40)
        self.assertTrue(ListeningSection.objects.get(test=test, number=1).audio.name)

    def test_missing_audio_is_an_import_error(self):
        (self.base_dir / "section-3.mp3").unlink()
        with self.assertRaises(SchemaError) as context:
            load_test(sample_payload(), base_dir=self.base_dir)
        self.assertIn("section 3.audio_file", str(context.exception))
        self.assertFalse(ListeningTest.objects.exists())

    def test_missing_image_is_a_warning_and_import_continues(self):
        payload = sample_payload()
        payload["sections"][0]["groups"][0]["image_file"] = "missing-map.png"
        test = load_test(payload, base_dir=self.base_dir)
        self.assertTrue(any("missing-map.png" in warning for warning in test.import_warnings))
        group = test.sections.get(number=1).groups.get()
        self.assertFalse(group.image)

    def test_existing_slug_requires_replace(self):
        load_test(sample_payload(), base_dir=self.base_dir)
        with self.assertRaisesRegex(AlreadyExists, "already exists"):
            load_test(sample_payload(), base_dir=self.base_dir)
