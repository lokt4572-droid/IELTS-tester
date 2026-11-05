from django.test import SimpleTestCase

from listening.schema import SchemaError, clean_payload


def sample_payload():
    sections = []
    number = 1
    for section_number in range(1, 5):
        questions = []
        for _ in range(10):
            questions.append({
                "number": number,
                "text": f"Answer ____ for question {number}",
                "answer": f"answer{number}",
            })
            number += 1
        sections.append({
            "number": section_number,
            "title": f"Section {section_number}",
            "context": "A sample listening section.",
            "audio_file": f"section-{section_number}.mp3",
            "audio_seconds": 400,
            "groups": [{
                "type": "completion",
                "instruction": "Complete each note.",
                "questions": questions,
            }],
        })
    return {
        "title": "Sample Listening Test",
        "source_name": "Test source",
        "license_note": "Used with permission.",
        "sections": sections,
    }


class ListeningSchemaTests(SimpleTestCase):
    def test_defaults_and_cleaned_fields(self):
        clean = clean_payload(sample_payload())
        self.assertEqual(clean["slug"], "sample-listening-test")
        self.assertEqual(clean["duration_minutes"], 30)
        self.assertEqual(clean["review_seconds"], 120)
        self.assertEqual(len(clean["sections"]), 4)
        self.assertEqual(clean["sections"][0]["groups"][0]["questions"][0]["number"], 1)

    def test_unknown_fields_are_reported_as_warnings(self):
        payload = sample_payload()
        payload["not_a_field"] = "ignored"
        payload["sections"][0]["unexpected"] = True
        clean = clean_payload(payload)
        self.assertEqual(len(clean["warnings"]), 2)
        self.assertTrue(any("not_a_field" in warning for warning in clean["warnings"]))

    def test_question_number_gap_is_rejected(self):
        payload = sample_payload()
        payload["sections"][0]["groups"][0]["questions"][0]["number"] = 2
        with self.assertRaises(SchemaError) as context:
            clean_payload(payload)
        self.assertTrue(any("question numbers must run 1 through 40" in e
                            for e in context.exception.errors))

    def test_completion_requires_blank_marker(self):
        payload = sample_payload()
        payload["sections"][0]["groups"][0]["questions"][0]["text"] = "What is the answer?"
        with self.assertRaises(SchemaError) as context:
            clean_payload(payload)
        self.assertTrue(any("must contain ____" in e for e in context.exception.errors))

    def test_mcq_multi_group_is_expanded_to_questions(self):
        payload = sample_payload()
        sections = payload["sections"]
        sections[0]["groups"] = [
            {
                "type": "mcq_multi",
                "instruction": "Choose TWO letters.",
                "choose": 2,
                "numbers": [1, 2],
                "text": "Which TWO facilities are available?",
                "options": [
                    {"key": "A", "text": "A"},
                    {"key": "B", "text": "B"},
                    {"key": "C", "text": "C"},
                ],
                "answers": ["A", "C"],
            },
            {
                "type": "completion",
                "instruction": "Complete the notes.",
                "questions": [
                    {
                        "number": number,
                        "text": f"Answer ____ for question {number}",
                        "answer": f"answer{number}",
                    }
                    for number in range(3, 11)
                ],
            },
        ]
        clean = clean_payload(payload)
        group = clean["sections"][0]["groups"][0]
        self.assertEqual(group["multi_question_numbers"], [1, 2])
        self.assertEqual([q["answer"] for q in group["questions"]], ["A", "C"])

