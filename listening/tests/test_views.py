import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from listening.models import (
    ListeningAttempt,
    ListeningGroup,
    ListeningQuestion,
    ListeningSection,
    ListeningTest,
)


class ListeningPracticeViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="listener",
            password="test-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-listener",
            password="test-password",
        )
        self.test = ListeningTest.objects.create(
            title="Practice test",
            slug="practice-test",
            is_published=True,
        )
        self.section = ListeningSection.objects.create(
            test=self.test,
            number=1,
            title="Section 1",
            audio="listening/audio/test.mp3",
            audio_seconds=60,
        )
        self.attempt = ListeningAttempt.objects.create(
            user=self.user,
            test=self.test,
            mode="practice",
        )
        self.client.force_login(self.user)
        self._create_question(
            "mcq",
            1,
            "B",
            question_options=[
                {"key": "A", "text": "Option A"},
                {"key": "B", "text": "Option B"},
            ],
        )
        multi_group = ListeningGroup.objects.create(
            section=self.section,
            order=2,
            qtype="mcq_multi",
            options=[
                {"key": "A", "text": "Option A"},
                {"key": "B", "text": "Option B"},
                {"key": "C", "text": "Option C"},
            ],
            choose=2,
            multi_question_numbers=[2, 3],
            multi_answers=["A", "C"],
        )
        for number, answer in ((2, "A"), (3, "C")):
            ListeningQuestion.objects.create(
                test=self.test,
                group=multi_group,
                number=number,
                text="Which two choices?",
                answer=answer,
            )
        self._create_question(
            "matching",
            4,
            "B",
            group_options=[
                {"key": "A", "text": "First"},
                {"key": "B", "text": "Second"},
            ],
        )
        self._create_question("completion", 5, "north gate", max_words=2)
        self._create_question("short", 6, "7 am")
        self._create_question(
            "diagram_label",
            7,
            "A",
            group_options=[
                {"key": "A", "text": "A"},
                {"key": "B", "text": "B"},
            ],
        )

    def _create_question(
        self,
        qtype,
        number,
        answer,
        *,
        question_options=None,
        group_options=None,
        choose=None,
        multi_numbers=None,
        multi_answers=None,
        max_words=None,
    ):
        group = ListeningGroup.objects.create(
            section=self.section,
            order=number,
            qtype=qtype,
            options=group_options or [],
            choose=choose,
            multi_question_numbers=multi_numbers or [],
            multi_answers=multi_answers or [],
            max_words=max_words,
        )
        return ListeningQuestion.objects.create(
            test=self.test,
            group=group,
            number=number,
            text=f"Question {number}",
            answer=answer,
            options=question_options or [],
        )

    def _post_json(self, url, answers):
        return self.client.post(
            url,
            data=json.dumps({"answers": answers}),
            content_type="application/json",
        )

    def test_attempt_page_shows_one_section_audio_and_question_types(self):
        response = self.client.get(reverse("listening:attempt", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Practice mode")
        self.assertContains(response, "<audio", html=False)
        self.assertContains(response, "Choose up to 2")
        self.assertNotContains(response, "transcript")
        self.assertNotContains(response, "Answer:")

    def test_answers_for_each_question_type_are_saved(self):
        response = self._post_json(
            reverse("listening:save", args=[self.attempt.pk]),
            {
                "1": "b",
                "2": ["A", "C"],
                "3": ["A", "C"],
                "4": "B",
                "5": "north gate",
                "6": "7 am",
                "7": "A",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        values = dict(
            self.attempt.answers.values_list("question_number", "value")
        )
        self.assertEqual(values, {
            1: "B",
            2: "A,C",
            3: "A,C",
            4: "B",
            5: "north gate",
            6: "7 am",
            7: "A",
        })

    def test_unknown_question_number_is_rejected(self):
        response = self._post_json(
            reverse("listening:save", args=[self.attempt.pk]),
            {"999": "A"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown question number", response.json()["error"])

    def test_multiselect_cannot_exceed_choose_limit(self):
        response = self._post_json(
            reverse("listening:save", args=[self.attempt.pk]),
            {"2": ["A", "B", "C"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("no more than 2", response.json()["error"])

    def test_multiselect_questions_share_one_selected_set(self):
        response = self._post_json(
            reverse("listening:save", args=[self.attempt.pk]),
            {"2": ["A", "B"], "3": ["B", "C"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("share one answer set", response.json()["error"])

    def test_text_over_200_characters_is_rejected(self):
        response = self._post_json(
            reverse("listening:save", args=[self.attempt.pk]),
            {"5": "x" * 201},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("200 characters", response.json()["error"])

    def test_letters_outside_the_question_options_are_rejected(self):
        response = self._post_json(
            reverse("listening:save", args=[self.attempt.pk]),
            {"1": "Z"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("listed option letters", response.json()["error"])

    def test_another_users_attempt_returns_404(self):
        other_attempt = ListeningAttempt.objects.create(
            user=self.other_user,
            test=self.test,
            mode="practice",
        )
        response = self._post_json(
            reverse("listening:save", args=[other_attempt.pk]),
            {"1": "A"},
        )
        self.assertEqual(response.status_code, 404)

    def test_save_is_rejected_after_submission(self):
        self.attempt.status = "submitted"
        self.attempt.save(update_fields=["status"])
        response = self._post_json(
            reverse("listening:save", args=[self.attempt.pk]),
            {"1": "A"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("already been submitted", response.json()["error"])

    def test_submit_marks_answers_and_is_idempotent(self):
        answers = {
            "1": "B",
            "2": ["A", "C"],
            "3": ["A", "C"],
            "4": "B",
            "5": "north gate",
            "6": "7 am",
            "7": "A",
        }
        response = self._post_json(
            reverse("listening:submit", args=[self.attempt.pk]),
            answers,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("listening:result", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "submitted")
        self.assertEqual(self.attempt.raw_score, 7)
        self.assertIsNone(self.attempt.band)
        self.assertTrue(all(
            answer.is_correct for answer in self.attempt.answers.all()
        ))

        original_submitted_at = self.attempt.submitted_at
        response = self._post_json(
            reverse("listening:submit", args=[self.attempt.pk]),
            {"1": "A"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("listening:result", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.raw_score, 7)
        self.assertEqual(self.attempt.submitted_at, original_submitted_at)

    def test_band_is_set_only_for_exactly_40_questions(self):
        test_40, attempt_40 = self._make_short_answer_attempt("forty-questions", 40)
        response = self._post_json(
            reverse("listening:submit", args=[attempt_40.pk]),
            {str(number): "correct" for number in range(1, 41)},
        )
        self.assertEqual(response.status_code, 302)
        attempt_40.refresh_from_db()
        self.assertEqual(attempt_40.raw_score, 40)
        self.assertEqual(str(attempt_40.band), "9.0")

        test_39, attempt_39 = self._make_short_answer_attempt("thirty-nine", 39)
        response = self._post_json(
            reverse("listening:submit", args=[attempt_39.pk]),
            {str(number): "correct" for number in range(1, 40)},
        )
        self.assertEqual(response.status_code, 302)
        attempt_39.refresh_from_db()
        self.assertEqual(attempt_39.raw_score, 39)
        self.assertIsNone(attempt_39.band)
        self.assertNotEqual(test_40.pk, test_39.pk)

    def _make_short_answer_attempt(self, slug, question_count):
        test = ListeningTest.objects.create(title=slug, slug=slug, is_published=True)
        section = ListeningSection.objects.create(
            test=test,
            number=1,
            title="Section 1",
            audio="listening/audio/test.mp3",
            audio_seconds=60,
        )
        group = ListeningGroup.objects.create(
            section=section,
            order=1,
            qtype="short",
        )
        ListeningQuestion.objects.bulk_create([
            ListeningQuestion(
                test=test,
                group=group,
                number=number,
                text=f"Question {number}",
                answer="correct",
            )
            for number in range(1, question_count + 1)
        ])
        attempt = ListeningAttempt.objects.create(
            user=self.user,
            test=test,
            mode="practice",
        )
        return test, attempt
