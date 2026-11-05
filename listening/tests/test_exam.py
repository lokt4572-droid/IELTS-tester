import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from listening.models import (
    ListeningAnswer,
    ListeningAttempt,
    ListeningGroup,
    ListeningQuestion,
    ListeningSection,
    ListeningTest,
)
from listening.phase import build_schedule, phase_at


class ListeningExamTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="exam-listener",
            password="test-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="exam-other",
            password="test-password",
        )
        self.test = ListeningTest.objects.create(
            title="Exam test",
            slug="exam-test",
            review_seconds=5,
            is_published=True,
        )
        self.sections = []
        self.questions = []
        for section_number in (1, 2):
            section = ListeningSection.objects.create(
                test=self.test,
                number=section_number,
                title=f"Section {section_number}",
                audio=f"listening/audio/{section_number}.mp3",
                audio_seconds=3,
                preview_seconds=2,
                check_seconds=4,
            )
            self.sections.append(section)
            group = ListeningGroup.objects.create(
                section=section,
                order=1,
                qtype="completion",
            )
            self.questions.append(ListeningQuestion.objects.create(
                test=self.test,
                group=group,
                number=section_number,
                text=f"Question {section_number} ____",
                answer=f"answer{section_number}",
            ))
        self.attempt = ListeningAttempt.objects.create(
            user=self.user,
            test=self.test,
            mode="exam",
        )
        self.client.force_login(self.user)

    def _post(self, route, data=None, attempt=None):
        attempt = attempt or self.attempt
        return self.client.post(
            reverse(route, args=[attempt.pk]),
            data=json.dumps(data or {}),
            content_type="application/json",
        )

    def test_phase_at_all_exact_boundaries(self):
        self.assertEqual(phase_at(self.attempt)["phase"], "ready")
        start = timezone.now()
        self.attempt.exam_started_at = start
        expected = [
            ("preview", 1),
            ("listen", 1),
            ("check", 1),
            ("preview", 2),
            ("listen", 2),
            ("check", 2),
            ("review", None),
        ]
        cursor = start
        schedule = build_schedule(self.attempt)
        self.assertEqual(len(schedule), 7)
        for index, (phase, section_number) in enumerate(expected):
            self.assertEqual(
                phase_at(self.attempt, cursor)["phase"],
                phase,
            )
            self.assertEqual(
                phase_at(self.attempt, cursor)["section_number"],
                section_number,
            )
            end = cursor + timedelta(seconds=schedule[index]["duration_seconds"])
            next_phase = phase_at(self.attempt, end)
            if index + 1 < len(expected):
                self.assertEqual(next_phase["phase"], expected[index + 1][0])
            else:
                self.assertEqual(next_phase["phase"], "finished")
            cursor = end
        self.assertEqual(phase_at(self.attempt, cursor + timedelta(seconds=1))["phase"], "finished")

    def test_begin_sets_start_once_and_returns_schedule(self):
        url = reverse("listening:exam_begin", args=[self.attempt.pk])
        first = self.client.post(url, data="{}", content_type="application/json")
        self.assertEqual(first.status_code, 200, msg=first.content.decode())
        self.assertTrue(first.json()["ok"])
        self.assertEqual(first.json()["phase"], "preview")
        self.assertEqual(len(first.json()["schedule"]), 7)
        self.attempt.refresh_from_db()
        started_at = self.attempt.exam_started_at

        second = self.client.post(url, data="{}", content_type="application/json")
        self.assertEqual(second.status_code, 200, msg=second.content.decode())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.exam_started_at, started_at)

    def test_exam_page_is_ready_then_loads_timeline_after_begin(self):
        response = self.client.get(reverse("listening:attempt", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.assertContains(response, "Begin test")
        self.assertContains(response, "ls-exam-audio")
        self.assertContains(response, "Volume")

        self._post("listening:exam_begin")
        response = self.client.get(reverse("listening:attempt", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.assertContains(response, 'data-begun="true"')

    def test_save_allowed_for_active_section_and_rejected_for_future_section(self):
        self.attempt.exam_started_at = timezone.now()
        self.attempt.save(update_fields=["exam_started_at"])
        response = self._post("listening:save", {"answers": {"1": "draft"}})
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.assertTrue(response.json()["schedule"])

        response = self._post("listening:save", {"answers": {"2": "future"}})
        self.assertEqual(response.status_code, 409, msg=response.content.decode())
        self.assertIn("not editable", response.json()["error"])

    def test_save_allowed_during_listen_and_check_phases(self):
        for elapsed in (2.5, 5.5):
            with self.subTest(elapsed=elapsed):
                self.attempt.exam_started_at = timezone.now() - timedelta(seconds=elapsed)
                self.attempt.save(update_fields=["exam_started_at"])
                self.assertIn(phase_at(self.attempt)["phase"], {"listen", "check"})
                response = self._post("listening:save", {"answers": {"1": "draft"}})
                self.assertEqual(response.status_code, 200, msg=response.content.decode())

    def test_review_phase_allows_saves_for_all_sections(self):
        self.attempt.exam_started_at = timezone.now() - timedelta(seconds=20)
        self.attempt.save(update_fields=["exam_started_at"])
        self.assertEqual(phase_at(self.attempt)["phase"], "review")
        response = self._post(
            "listening:save",
            {"answers": {"1": "draft 1", "2": "draft 2"}},
        )
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.assertEqual(ListeningAnswer.objects.filter(attempt=self.attempt).count(), 2)

    def test_save_after_end_lazily_submits_and_scores_once(self):
        ListeningAnswer.objects.create(
            attempt=self.attempt,
            question_number=1,
            value="answer1",
        )
        elapsed = 2 + 3 + 4 + 2 + 3 + 4 + self.test.review_seconds
        self.attempt.exam_started_at = timezone.now() - timedelta(seconds=elapsed + 1)
        self.attempt.save(update_fields=["exam_started_at"])
        response = self._post("listening:save", {"answers": {"1": "answer1"}})
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.assertTrue(response.json()["finished"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "submitted")
        self.assertEqual(self.attempt.raw_score, 1)
        self.assertTrue(self.attempt.answers.get(question_number=1).is_correct)
        submitted_at = self.attempt.submitted_at

        response = self.client.get(
            reverse("listening:exam_state", args=[self.attempt.pk])
        )
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.submitted_at, submitted_at)

    def test_page_load_after_exam_end_lazily_finalizes(self):
        elapsed = 2 + 3 + 4 + 2 + 3 + 4 + self.test.review_seconds
        self.attempt.exam_started_at = timezone.now() - timedelta(seconds=elapsed + 1)
        self.attempt.save(update_fields=["exam_started_at"])
        response = self.client.get(reverse("listening:attempt", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 302, msg=response.content.decode())
        self.assertEqual(response.url, reverse("listening:result", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "submitted")

    def test_exam_attempt_is_private(self):
        other_attempt = ListeningAttempt.objects.create(
            user=self.other_user,
            test=self.test,
            mode="exam",
        )
        response = self.client.get(reverse("listening:attempt", args=[other_attempt.pk]))
        self.assertEqual(response.status_code, 404, msg=response.content.decode())

    def test_practice_attempt_does_not_receive_exam_schedule(self):
        practice = ListeningAttempt.objects.create(
            user=self.user,
            test=self.test,
            mode="practice",
        )
        response = self.client.get(reverse("listening:attempt", args=[practice.pk]))
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.assertContains(response, "Practice mode")
        self.assertNotContains(response, "Begin test")
