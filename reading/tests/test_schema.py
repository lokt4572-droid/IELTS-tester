import copy
import json
import unittest
from pathlib import Path

from reading.schema import SchemaError, clean_payload

SAMPLE = Path(__file__).resolve().parents[2] / "sample_data" / "demo_system_check.json"


def load():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


class SchemaTests(unittest.TestCase):
    def test_demo_file_is_valid(self):
        clean = clean_payload(load())
        numbers = [q["number"] for p in clean["passages"] for g in p["groups"] for q in g["questions"]]
        self.assertEqual(numbers, list(range(1, 9)))
        self.assertEqual(clean["translations"], {})
        self.assertEqual(clean["translation_warnings"], [])

    def test_translations_are_kept_when_valid(self):
        data = load()
        translations = {
            "ru": {
                "words": {"abandon": {"t": "покинуть"}},
                "forms": {"abandoned": "abandon"},
            }
        }
        data["translations"] = translations

        clean = clean_payload(data)

        self.assertEqual(clean["translations"], translations)
        self.assertEqual(clean["translation_warnings"], [])

    def test_invalid_translations_are_skipped_without_rejecting_test(self):
        data = load()
        data["translations"] = {"ru": {"words": []}}

        clean = clean_payload(data)

        self.assertEqual(clean["translations"], {})
        self.assertEqual(len(clean["passages"]), 1)
        self.assertIn("translations.ru.words must be an object", clean["translation_warnings"][0])

    def test_non_object_translations_are_skipped(self):
        data = load()
        data["translations"] = []

        clean = clean_payload(data)

        self.assertEqual(clean["translations"], {})
        self.assertIn("translations must be an object", clean["translation_warnings"][0])

    def test_tfng_aliases_are_normalised(self):
        data = load()
        data["passages"][0]["groups"][0]["questions"][0]["answer"] = "t"
        clean = clean_payload(data)
        self.assertEqual(clean["passages"][0]["groups"][0]["questions"][0]["answer"], "TRUE")

    def test_missing_source_is_rejected(self):
        data = load()
        data["source_name"] = ""
        data["license_note"] = ""
        with self.assertRaises(SchemaError) as ctx:
            clean_payload(data)
        self.assertTrue(any("source_name" in e for e in ctx.exception.errors))
        self.assertTrue(any("license_note" in e for e in ctx.exception.errors))

    def test_bad_numbering(self):
        data = load()
        data["passages"][0]["groups"][0]["questions"][1]["number"] = 5
        with self.assertRaises(SchemaError):
            clean_payload(data)

    def test_mcq_answer_must_match_option(self):
        data = load()
        data["passages"][0]["groups"][1]["questions"][0]["answer"] = "Z"
        with self.assertRaises(SchemaError):
            clean_payload(data)

    def test_matching_needs_options(self):
        data = load()
        data["passages"][0]["groups"][2]["options"] = []
        with self.assertRaises(SchemaError):
            clean_payload(data)

    def test_all_errors_reported_together(self):
        data = copy.deepcopy(load())
        data["title"] = ""
        data["passages"][0]["text"] = ""
        with self.assertRaises(SchemaError) as ctx:
            clean_payload(data)
        self.assertGreaterEqual(len(ctx.exception.errors), 2)

    def test_not_an_object(self):
        with self.assertRaises(SchemaError):
            clean_payload([])


if __name__ == "__main__":
    unittest.main()
