import unittest
from unittest import mock

from django.test import override_settings

from chat import gemini


def fake(status=200, payload=None):
    r = mock.Mock()
    r.status_code = status
    r.text = "body"
    r.json.return_value = payload if payload is not None else {}
    return r


OK = {"candidates": [{"content": {"parts": [{"text": " Hello there. "}]}}]}


class GeminiTests(unittest.TestCase):
    def test_payload_maps_roles(self):
        p = gemini.build_payload([{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
        self.assertEqual([c["role"] for c in p["contents"]], ["user", "model"])
        self.assertIn("systemInstruction", p)

    def test_success_and_key_in_header_not_url(self):
        with mock.patch("requests.post", return_value=fake(200, OK)) as post:
            text = gemini.generate_reply([{"role": "user", "content": "hi"}], api_key="SECRET", model="m1")
        self.assertEqual(text, "Hello there.")
        url = post.call_args.args[0]
        self.assertNotIn("SECRET", url)
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "SECRET")
        self.assertIn("m1:generateContent", url)

    def test_missing_key(self):
        with self.assertRaises(gemini.GeminiError):
            gemini.generate_reply([], api_key="", model="m")

    def test_http_errors(self):
        for status in (429, 403, 404, 500):
            with (
                mock.patch("requests.post", return_value=fake(status)),
                mock.patch("chat.gemini.time.sleep"),
            ):
                with self.assertRaises(gemini.GeminiError):
                    gemini.generate_reply([{"role": "user", "content": "x"}], api_key="k", model="m")

    def test_blocked_and_empty(self):
        with mock.patch("requests.post", return_value=fake(200, {"promptFeedback": {"blockReason": "SAFETY"}})):
            with self.assertRaises(gemini.GeminiError):
                gemini.generate_reply([{"role": "user", "content": "x"}], api_key="k", model="m")
        with mock.patch("requests.post", return_value=fake(200, {"candidates": []})):
            with self.assertRaises(gemini.GeminiError):
                gemini.generate_reply([{"role": "user", "content": "x"}], api_key="k", model="m")

    def test_thought_parts_are_skipped(self):
        data = {"candidates": [{"content": {"parts": [
            {"text": "hidden", "thought": True},
            {"thoughtSignature": "private-signature"},
            {"text": "shown"},
        ]}}]}
        self.assertEqual(gemini.extract_text(data), "shown")

    def test_timeout(self):
        import requests
        with mock.patch("requests.post", side_effect=requests.Timeout):
            with self.assertRaises(gemini.GeminiError):
                gemini.generate_reply([{"role": "user", "content": "x"}], api_key="k", model="m")

    @override_settings(GEMINI_THINKING_LEVEL="low", GEMINI_THINKING_BUDGET=None)
    def test_thinking_level_is_sent(self):
        config = gemini.build_payload([])["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "low"})

    @override_settings(GEMINI_THINKING_LEVEL=None, GEMINI_THINKING_BUDGET=512)
    def test_thinking_budget_is_sent(self):
        config = gemini.build_payload([])["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingBudget": 512})

    @override_settings(GEMINI_THINKING_LEVEL=None, GEMINI_THINKING_BUDGET=0)
    def test_zero_thinking_budget_is_sent(self):
        config = gemini.build_payload([])["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingBudget": 0})

    @override_settings(GEMINI_THINKING_LEVEL="medium", GEMINI_THINKING_BUDGET=512)
    def test_thinking_level_takes_precedence_over_budget(self):
        config = gemini.build_payload([])["generationConfig"]
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "medium"})

    @override_settings(GEMINI_THINKING_LEVEL=None, GEMINI_THINKING_BUDGET=None)
    def test_thinking_config_is_omitted_when_unset(self):
        config = gemini.build_payload([])["generationConfig"]
        self.assertNotIn("thinkingConfig", config)

    @override_settings(GEMINI_TIMEOUT_SECONDS=17)
    def test_timeout_setting_is_used(self):
        with mock.patch("requests.post", return_value=fake(200, OK)) as post:
            gemini.generate_reply(
                [{"role": "user", "content": "hello"}],
                api_key="test-key",
                model="test-model",
            )
        self.assertEqual(post.call_args.kwargs["timeout"], 17)

    @override_settings(GEMINI_503_RETRIES=2)
    def test_503_then_200_succeeds_with_two_requests(self):
        with (
            mock.patch("requests.post", side_effect=[fake(503), fake(200, OK)]) as post,
            mock.patch("chat.gemini.time.sleep") as sleep,
        ):
            result = gemini.generate_reply(
                [{"role": "user", "content": "hello"}],
                api_key="test-key",
                model="test-model",
            )
        self.assertEqual(result, "Hello there.")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    @override_settings(GEMINI_503_RETRIES=2)
    def test_503_retries_twice_then_raises_friendly_error(self):
        with (
            mock.patch("requests.post", side_effect=[fake(503), fake(503), fake(503)]) as post,
            mock.patch("chat.gemini.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(
                gemini.GeminiError,
                "The AI service had a problem. Please try again.",
            ):
                gemini.generate_reply(
                    [{"role": "user", "content": "hello"}],
                    api_key="test-key",
                    model="test-model",
                )
        self.assertEqual(post.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_429_is_not_retried(self):
        with (
            mock.patch("requests.post", return_value=fake(429)) as post,
            mock.patch("chat.gemini.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(
                gemini.GeminiError,
                "busy or its quota is used up",
            ):
                gemini.generate_reply(
                    [{"role": "user", "content": "hello"}],
                    api_key="test-key",
                    model="test-model",
                )
        post.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
