"""End-to-end tests. Run with: python manage.py test"""
import json
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from chat.gemini import GeminiError
from chat.models import ChatMessage, ChatSession
from reading.importer import AlreadyExists, load_test
from reading.models import Attempt, Question

SAMPLE = Path(__file__).resolve().parents[2] / "sample_data" / "demo_system_check.json"


def make_test(publish=True):
    return load_test(json.loads(SAMPLE.read_text(encoding="utf-8")), publish=publish)


class ImportTests(TestCase):
    def test_import_counts(self):
        test = make_test()
        self.assertEqual(test.question_count(), 8)
        self.assertEqual(test.passages.count(), 1)

    def test_duplicate_slug_needs_replace(self):
        make_test()
        with self.assertRaises(AlreadyExists):
            make_test()
        load_test(json.loads(SAMPLE.read_text(encoding="utf-8")), replace=True, publish=True)

    def test_import_saves_optional_translations(self):
        data = json.loads(SAMPLE.read_text(encoding="utf-8"))
        data["translations"] = {
            "ru": {
                "words": {"carry out": {"t": "выполнять", "pos": "phrase"}},
                "forms": {"carried out": "carry out"},
            }
        }

        test = load_test(data)

        self.assertEqual(test.translations, data["translations"])

    def test_import_skips_invalid_translations_only(self):
        data = json.loads(SAMPLE.read_text(encoding="utf-8"))
        data["translations"] = {"ru": {"words": []}}

        test = load_test(data)

        self.assertEqual(test.translations, {})
        self.assertEqual(test.passages.count(), 1)
        self.assertTrue(test.import_warnings)


class ReadingFlowTests(TestCase):
    def setUp(self):
        self.test = make_test()
        self.user = User.objects.create_user("sam", password="pw-12345-xyz")
        self.client.login(username="sam", password="pw-12345-xyz")

    def start(self):
        resp = self.client.post(reverse("reading:start", args=[self.test.slug]))
        attempt = Attempt.objects.get(user=self.user)
        self.assertRedirects(resp, reverse("reading:attempt", args=[attempt.pk]))
        return attempt

    def answers_for(self, attempt, wrong=()):
        data = {}
        for q in Question.objects.filter(group__passage__test=self.test):
            right = q.answer.split("|")[0]
            data[f"q_{q.id}"] = "WRONG" if q.number in wrong else right
        return data

    def test_public_pages(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("tests_hub")).status_code, 200)
        self.assertContains(self.client.get(reverse("reading:list")), self.test.title)
        self.assertEqual(self.client.get(reverse("reading:detail", args=[self.test.slug])).status_code, 200)

    def test_unpublished_test_is_hidden(self):
        self.test.is_published = False
        self.test.save()
        self.assertEqual(self.client.get(reverse("reading:detail", args=[self.test.slug])).status_code, 404)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.post(reverse("reading:start", args=[self.test.slug]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_attempt_page_renders_all_question_types(self):
        attempt = self.start()
        resp = self.client.get(reverse("reading:attempt", args=[attempt.pk]))
        self.assertContains(resp, "Power from the tides")
        self.assertContains(resp, 'id="reading-translations" type="application/json">{}</script>')
        self.assertContains(resp, "js/hover-translate.js")
        self.assertContains(resp, 'type="radio"')
        self.assertContains(resp, "<select")
        self.assertContains(resp, 'class="gap"')

    def test_attempt_page_embeds_translation_json_safely(self):
        self.test.translations = {
            "ru": {"words": {"abandon": {"t": "покинуть"}}}
        }
        self.test.save(update_fields=["translations"])
        attempt = self.start()

        response = self.client.get(reverse("reading:attempt", args=[attempt.pk]))

        self.assertContains(response, 'id="reading-translations" type="application/json"')
        self.assertContains(response, r"\u043f\u043e\u043a\u0438\u043d\u0443\u0442\u044c")

    def test_start_twice_resumes(self):
        attempt = self.start()
        self.client.post(reverse("reading:start", args=[self.test.slug]))
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 1)

    def test_autosave_then_submit_perfect_score(self):
        attempt = self.start()
        data = self.answers_for(attempt)
        resp = self.client.post(reverse("reading:save", args=[attempt.pk]), data)
        self.assertEqual(resp.json()["answered"], 8)
        resp = self.client.post(reverse("reading:submit", args=[attempt.pk]), data)
        self.assertRedirects(resp, reverse("reading:result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual((attempt.score, attempt.total), (8, 8))
        self.assertEqual(str(attempt.band), "9.0")

    def test_wrong_and_blank_answers(self):
        attempt = self.start()
        data = self.answers_for(attempt, wrong=(1, 4))
        q8 = Question.objects.get(group__passage__test=self.test, number=8)
        del data[f"q_{q8.id}"]  # leave question 8 blank
        self.client.post(reverse("reading:submit", args=[attempt.pk]), data)
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 5)
        page = self.client.get(reverse("reading:result", args=[attempt.pk]))
        self.assertContains(page, "Incorrect")
        self.assertContains(page, "(blank)")

    def test_cannot_resubmit_or_save_after_finish(self):
        attempt = self.start()
        self.client.post(reverse("reading:submit", args=[attempt.pk]), {})
        attempt.refresh_from_db()
        first = attempt.finished_at
        self.client.post(reverse("reading:submit", args=[attempt.pk]), self.answers_for(attempt))
        attempt.refresh_from_db()
        self.assertEqual(attempt.finished_at, first)
        self.assertEqual(attempt.score, 0)
        resp = self.client.post(reverse("reading:save", args=[attempt.pk]), {})
        self.assertEqual(resp.status_code, 409)

    def test_other_users_cannot_see_attempt(self):
        attempt = self.start()
        User.objects.create_user("eve", password="pw-12345-xyz")
        self.client.login(username="eve", password="pw-12345-xyz")
        self.assertEqual(self.client.get(reverse("reading:attempt", args=[attempt.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("reading:result", args=[attempt.pk])).status_code, 404)

    def test_expired_attempt_is_graded_automatically(self):
        attempt = self.start()
        data = self.answers_for(attempt)
        self.client.post(reverse("reading:save", args=[attempt.pk]), data)
        from datetime import timedelta
        from django.utils import timezone
        Attempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(hours=2))
        resp = self.client.get(reverse("reading:attempt", args=[attempt.pk]))
        self.assertRedirects(resp, reverse("reading:result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 8)

    def test_dashboard(self):
        attempt = self.start()
        self.client.post(reverse("reading:submit", args=[attempt.pk]), self.answers_for(attempt))
        self.assertContains(self.client.get(reverse("dashboard")), "tests finished")

    def test_signup_creates_user_and_logs_in(self):
        self.client.logout()
        resp = self.client.post(reverse("signup"), {
            "username": "newbie", "password1": "Tr1cky-pass-77", "password2": "Tr1cky-pass-77"})
        self.assertRedirects(resp, reverse("dashboard"))
        self.assertTrue(User.objects.filter(username="newbie").exists())


@override_settings(GEMINI_API_KEY="test-key", CHAT_DAILY_LIMIT=2)
class ChatTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("sam", password="pw-12345-xyz")
        self.client.login(username="sam", password="pw-12345-xyz")
        self.url = reverse("chat:send")

    def post(self, **body):
        return self.client.post(self.url, json.dumps(body), content_type="application/json")

    @mock.patch("chat.views.generate_reply", return_value="Use skimming.")
    def test_new_chat_saves_both_messages(self, gen):
        resp = self.post(message="How do I skim?")
        self.assertEqual(resp.json()["reply"], "Use skimming.")
        session = ChatSession.objects.get(user=self.user)
        self.assertEqual([m.role for m in session.messages.all()], ["user", "assistant"])
        self.assertEqual(self.client.get(reverse("chat:session", args=[session.pk])).status_code, 200)

    @mock.patch("chat.views.generate_reply", return_value="ok")
    def test_follow_up_sends_history(self, gen):
        sid = self.post(message="first").json()["session_id"]
        self.post(message="second", session_id=sid)
        history = gen.call_args.args[0]
        self.assertEqual([m["content"] for m in history], ["first", "ok", "second"])

    @mock.patch("chat.views.generate_reply", side_effect=GeminiError("busy"))
    def test_ai_failure_saves_nothing(self, gen):
        resp = self.post(message="hello")
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(ChatMessage.objects.count(), 0)

    @mock.patch("chat.views.generate_reply", return_value="ok")
    def test_daily_limit(self, gen):
        self.post(message="1")
        self.post(message="2")
        self.assertEqual(self.post(message="3").status_code, 429)

    def test_validation(self):
        self.assertEqual(self.post(message="  ").status_code, 400)
        self.assertEqual(self.post(message="x" * 5000).status_code, 400)

    @mock.patch("chat.views.generate_reply", return_value="ok")
    def test_cannot_use_someone_elses_session(self, gen):
        other = User.objects.create_user("eve", password="pw-12345-xyz")
        s = ChatSession.objects.create(user=other, title="x")
        self.assertEqual(self.post(message="hi", session_id=s.pk).status_code, 404)
        self.assertEqual(self.client.get(reverse("chat:session", args=[s.pk])).status_code, 404)

    @mock.patch("chat.views.generate_reply", return_value="Because paragraph B says 1966.")
    def test_explain_question_attaches_passage_context(self, gen):
        test = make_test()
        attempt = Attempt.objects.create(user=self.user, test=test)
        from reading.services import finish_attempt
        finish_attempt(attempt, {})
        q = Question.objects.get(group__passage__test=test, number=2)
        self.post(message="Why?", attempt=attempt.pk, question=q.pk)
        sent = gen.call_args.args[0][-1]["content"]
        self.assertIn("Power from the tides", sent)
        self.assertIn("Correct answer: FALSE", sent)
        saved = ChatMessage.objects.get(role="user")
        self.assertEqual(saved.content, "Why?")
        self.assertIn("1966", saved.context)

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.post(message="hi").status_code, 302)
