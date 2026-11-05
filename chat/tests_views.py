import json
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from chat import groq as chat_groq
from chat import providers
from chat.groq import GroqChatError
from chat.providers import ChatProviderError
from chat.models import ChatMessage, ChatSession


def groq_response(payload, status=200):
    response = mock.Mock()
    response.status_code = status
    response.headers = {}
    response.json.return_value = payload
    response.text = "provider error"
    return response


class ChatProviderTests(TestCase):
    def test_provider_whitelist(self):
        self.assertEqual(set(providers.PROVIDERS), {"groq", "gemini"})

    @override_settings(
        GROQ_API_KEY="test-key",
        GROQ_CHAT_MODEL="openai/gpt-oss-20b",
        GROQ_CHAT_MAX_TOKENS=2000,
        GROQ_CHAT_REASONING_EFFORT="invalid",
    )
    def test_invalid_chat_reasoning_effort_names_chat_setting(self):
        with self.assertRaisesRegex(
            GroqChatError,
            "GROQ_CHAT_REASONING_EFFORT must be low, medium, or high.",
        ):
            chat_groq.generate_reply([{"role": "user", "content": "Question"}])

    def test_groq_history_conversion_has_system_then_user_assistant_history(self):
        messages = chat_groq.build_messages([
            {"role": "user", "content": "first user"},
            {"role": "assistant", "content": "assistant reply"},
            {"role": "user", "content": "next user"},
        ])
        self.assertEqual(messages[0], {
            "role": "system",
            "content": chat_groq.SYSTEM_PROMPT,
        })
        self.assertEqual(
            [(message["role"], message["content"]) for message in messages[1:]],
            [
                ("user", "first user"),
                ("assistant", "assistant reply"),
                ("user", "next user"),
            ],
        )

    @override_settings(
        GROQ_API_KEY="test-key",
        GROQ_CHAT_MODEL="openai/gpt-oss-20b",
        GROQ_CHAT_MAX_TOKENS=1234,
        GROQ_CHAT_REASONING_EFFORT="high",
    )
    def test_groq_request_uses_server_token_settings_and_hides_reasoning(self):
        payload = {
            "choices": [{
                "message": {
                    "content": "Visible answer",
                    "reasoning": "Private reasoning",
                },
                "finish_reason": "stop",
            }],
        }
        with (
            mock.patch("requests.post", return_value=groq_response(payload)) as post,
            mock.patch("time.sleep"),
        ):
            reply = chat_groq.generate_reply(
                [{"role": "user", "content": "Question"}]
            )

        self.assertEqual(reply, "Visible answer")
        request_data = post.call_args.kwargs["json"]
        self.assertEqual(request_data["max_tokens"], 1234)
        self.assertEqual(request_data["reasoning_effort"], "high")
        self.assertFalse(request_data["include_reasoning"])
        self.assertEqual(
            request_data["messages"][0],
            {"role": "system", "content": chat_groq.SYSTEM_PROMPT},
        )

    def test_groq_empty_truncated_reply_has_friendly_error(self):
        payload = {
            "choices": [{
                "message": {"content": ""},
                "finish_reason": "length",
            }],
        }
        with (
            override_settings(
                GROQ_API_KEY="test-key",
                GROQ_CHAT_MODEL="openai/gpt-oss-20b",
                GROQ_CHAT_MAX_TOKENS=2000,
                GROQ_CHAT_REASONING_EFFORT="low",
            ),
            mock.patch("requests.post", return_value=groq_response(payload)),
            mock.patch("time.sleep"),
        ):
            with self.assertRaisesRegex(GroqChatError, "The model ran out of tokens"):
                chat_groq.generate_reply([{"role": "user", "content": "Question"}])

    @override_settings(
        GROQ_API_KEY="private-chat-key",
        GROQ_CHAT_MODEL="openai/gpt-oss-20b",
        GROQ_CHAT_MAX_TOKENS=2000,
        GROQ_CHAT_REASONING_EFFORT="low",
    )
    def test_provider_key_echo_is_redacted_from_reply(self):
        payload = {
            "choices": [{
                "message": {"content": "Echo private-chat-key"},
                "finish_reason": "stop",
            }],
        }
        with mock.patch("requests.post", return_value=groq_response(payload)):
            reply = chat_groq.generate_reply([{"role": "user", "content": "Question"}])
        self.assertEqual(reply, "Echo [REDACTED]")

    @override_settings(
        GROQ_API_KEY="test-key",
        GROQ_CHAT_MODEL="openai/gpt-oss-20b",
        GROQ_CHAT_MAX_TOKENS=2000,
        GROQ_CHAT_REASONING_EFFORT="low",
    )
    def test_groq_transport_retries_and_respects_retry_after(self):
        rate_limited = groq_response({}, status=429)
        rate_limited.headers = {"Retry-After": "5"}
        success = groq_response({
            "choices": [{
                "message": {"content": "Recovered"},
                "finish_reason": "stop",
            }],
        })
        with (
            mock.patch("requests.post", side_effect=[rate_limited, success]) as post,
            mock.patch("time.sleep") as sleep,
        ):
            reply = chat_groq.generate_reply([{"role": "user", "content": "Question"}])
        self.assertEqual(reply, "Recovered")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(5.0)

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=True,
    )
    def test_groq_provider_failure_falls_back_to_gemini(self):
        with (
            mock.patch(
                "chat.providers.generate_groq_reply",
                side_effect=GroqChatError(
                    "Unavailable.", fallback_allowed=True, failure_reason="HTTP 503"
                ),
            ),
            mock.patch(
                "chat.providers.generate_gemini_reply",
                return_value="Backup answer",
            ) as gemini_reply,
            self.assertLogs("chat.providers", level="WARNING") as logs,
        ):
            reply = providers.generate_chat_reply([], "groq")
        self.assertEqual(reply, ("Backup answer", "gemini", "groq"))
        gemini_reply.assert_called_once_with([])
        self.assertIn("HTTP 503", "\n".join(logs.output))

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=False,
    )
    def test_groq_failure_does_not_fallback_when_disabled(self):
        with (
            mock.patch(
                "chat.providers.generate_groq_reply",
                side_effect=GroqChatError(
                    "Unavailable.", fallback_allowed=True, failure_reason="HTTP 429"
                ),
            ),
            mock.patch("chat.providers.generate_gemini_reply") as gemini_reply,
        ):
            with self.assertRaises(ChatProviderError):
                providers.generate_chat_reply([], "groq")
        gemini_reply.assert_not_called()

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=True,
    )
    def test_groq_configuration_error_does_not_fallback(self):
        with (
            mock.patch(
                "chat.providers.generate_groq_reply",
                side_effect=GroqChatError(
                    "The AI service rejected the request.",
                    failure_reason="HTTP 401",
                ),
            ),
            mock.patch("chat.providers.generate_gemini_reply") as gemini_reply,
            self.assertLogs("chat.providers", level="ERROR"),
        ):
            with self.assertRaises(ChatProviderError):
                providers.generate_chat_reply([], "groq")
        gemini_reply.assert_not_called()


class ChatSendViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="chat-user",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.url = reverse("chat:send")

    def post_json(self, data):
        return self.client.post(
            self.url,
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_login_required(self):
        self.client.logout()
        response = self.post_json({"message": "Hello", "provider": "groq"})
        self.assertEqual(response.status_code, 302)

    def test_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    @override_settings(
        CHAT_AI_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="",
        GROQ_CHAT_MODEL="chat-model",
        CHAT_DAILY_LIMIT=40,
    )
    def test_default_provider_response_and_saved_provider(self):
        with mock.patch(
            "chat.providers.generate_groq_reply",
            return_value="Hello back",
        ) as groq_reply:
            response = self.post_json({"message": "Hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Hello back")
        self.assertNotIn("provider_used", response.json())
        self.assertNotIn("fallback_from", response.json())
        groq_reply.assert_called_once()
        assistant = ChatMessage.objects.get(role="assistant")
        self.assertEqual(assistant.provider, "groq")
        self.assertEqual(assistant.model, "chat-model")
        self.assertEqual(ChatMessage.objects.filter(role="user").count(), 1)

    @override_settings(
        CHAT_AI_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="",
        CHAT_AI_FALLBACK_FROM_GROQ=False,
        CHAT_DAILY_LIMIT=40,
    )
    def test_provider_failure_does_not_consume_daily_message_slot(self):
        with mock.patch(
            "chat.providers.generate_groq_reply",
            side_effect=GroqChatError("Provider unavailable."),
        ):
            failed = self.post_json({"message": "First message"})
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(ChatMessage.objects.count(), 0)
        self.assertEqual(ChatSession.objects.count(), 0)

        with mock.patch(
            "chat.providers.generate_groq_reply",
            return_value="Successful reply",
        ):
            successful = self.post_json({"message": "Second message"})
        self.assertEqual(successful.status_code, 200)
        self.assertEqual(
            ChatMessage.objects.filter(role="user").count(),
            1,
        )

    @override_settings(
        CHAT_AI_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        CHAT_DAILY_LIMIT=1,
    )
    def test_daily_limit_applies_after_successful_provider_response(self):
        with mock.patch(
            "chat.providers.generate_groq_reply",
            return_value="First answer",
        ):
            first = self.post_json({"message": "First"})
        self.assertEqual(first.status_code, 200)

        with mock.patch("chat.providers.generate_groq_reply") as provider_reply:
            limited = self.post_json({"message": "Second"})
        self.assertEqual(limited.status_code, 429)
        provider_reply.assert_not_called()

    @override_settings(
        CHAT_AI_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        CHAT_DAILY_LIMIT=40,
    )
    def test_success_stores_provider_without_exposing_it(self):
        with mock.patch(
            "chat.providers.generate_groq_reply",
            return_value="Here is an answer",
        ):
            response = self.post_json({
                "message": "Hello",
                "provider": "groq",
            })
        self.assertNotIn("provider_used", response.json())
        self.assertNotContains(response, "Groq")
        self.assertNotContains(response, "Gemini")
        self.assertEqual(
            ChatMessage.objects.get(role="assistant").provider,
            "groq",
        )

    @override_settings(
        CHAT_AI_PROVIDER="groq",
        GROQ_API_KEY="groq-key",
        CHAT_DAILY_LIMIT=40,
    )
    def test_browser_provider_field_is_ignored(self):
        with mock.patch(
            "chat.providers.generate_groq_reply",
            return_value="Answer",
        ) as groq_reply:
            response = self.post_json({
                "message": "Hello",
                "provider": "gemini",
                "model": "attacker/model",
                "max_tokens": 1,
                "reasoning_effort": "high",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(groq_reply.call_args.args[0][-1]["content"], "Hello")
        self.assertNotIn("provider_used", response.json())
        self.assertNotIn("fallback_from", response.json())

    @override_settings(GROQ_API_KEY="groq-key", CHAT_AI_PROVIDER="groq")
    def test_switch_is_not_rendered_and_page_has_no_provider_names(self):
        response = self.client.get(reverse("chat:home"))
        self.assertNotContains(response, "chat-ai-switch")
        self.assertNotContains(response, "Groq")
        self.assertNotContains(response, "Gemini")

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_PROVIDER="groq",
    )
    def test_saved_provider_is_not_exposed_in_page_history(self):
        session = ChatSession.objects.create(user=self.user, title="Saved chat")
        ChatMessage.objects.create(
            session=session,
            role="assistant",
            content="Saved reply",
            provider="groq",
        )
        response = self.client.get(reverse("chat:session", args=[session.pk]))
        self.assertNotIn("provider", response.context["messages_json"][0])
        self.assertNotContains(response, "Groq")
        self.assertNotContains(response, "Gemini")

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=True,
        GEMINI_MODEL="backup-model",
        CHAT_DAILY_LIMIT=40,
        CHAT_AI_PROVIDER="groq",
        GEMINI_TIMEOUT_SECONDS=25,
        GEMINI_503_RETRIES=2,
        GEMINI_THINKING_LEVEL=None,
        GEMINI_THINKING_BUDGET=None,
    )
    def test_groq_transient_failures_fallback_through_endpoint(self):
        backup = groq_response({
            "candidates": [{"content": {"parts": [{"text": "Backup answer"}]}}],
        })
        cases = [
            ("503", [groq_response({}, 503), groq_response({}, 503), groq_response({}, 503), backup]),
            ("500", [groq_response({}, 500), groq_response({}, 500), groq_response({}, 500), backup]),
            ("429", [groq_response({}, 429), groq_response({}, 429), groq_response({}, 429), backup]),
            ("timeout", [requests.Timeout(), requests.Timeout(), requests.Timeout(), backup]),
            ("network", [requests.ConnectionError(), requests.ConnectionError(), requests.ConnectionError(), backup]),
        ]
        for failure_name, failures in cases:
            with self.subTest(failure=failure_name):
                with (
                    mock.patch(
                        "requests.post",
                        side_effect=failures,
                    ) as requests_post,
                    mock.patch("core.ai.groq_transport.time.sleep"),
                    mock.patch("chat.gemini.time.sleep"),
                ):
                    response = self.post_json({
                        "message": f"Question about {failure_name}",
                        "provider": "gemini",
                    })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["reply"], "Backup answer")
                self.assertNotIn("provider_used", response.json())
                self.assertNotIn("fallback_from", response.json())
                self.assertNotContains(response, "Groq")
                self.assertNotContains(response, "Gemini")
                self.assertEqual(requests_post.call_count, len(failures))
                saved = ChatMessage.objects.filter(role="assistant").latest("id")
                self.assertEqual(saved.provider, "gemini")
                self.assertEqual(saved.model, "backup-model")

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=True,
        CHAT_AI_PROVIDER="groq",
        GEMINI_MODEL="backup-model",
        CHAT_DAILY_LIMIT=40,
        GEMINI_TIMEOUT_SECONDS=25,
        GEMINI_503_RETRIES=0,
        GEMINI_THINKING_LEVEL=None,
        GEMINI_THINKING_BUDGET=None,
    )
    def test_groq_configuration_http_failures_do_not_fallback(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                with (
                    mock.patch("requests.post", return_value=groq_response({}, status)),
                    mock.patch("chat.providers.generate_gemini_reply") as gemini_reply,
                    self.assertLogs("chat.providers", level="ERROR"),
                ):
                    response = self.post_json({
                        "message": "Question",
                        "provider": "gemini",
                    })
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("Gemini", response.json()["error"])
                self.assertNotIn("Groq", response.json()["error"])
                gemini_reply.assert_not_called()

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=False,
        CHAT_AI_PROVIDER="groq",
        CHAT_DAILY_LIMIT=40,
        GEMINI_TIMEOUT_SECONDS=25,
        GEMINI_503_RETRIES=0,
        GEMINI_THINKING_LEVEL=None,
        GEMINI_THINKING_BUDGET=None,
    )
    def test_groq_failure_without_fallback_returns_friendly_error(self):
        with (
            mock.patch("requests.post", return_value=groq_response({}, 429)),
            mock.patch("core.ai.groq_transport.time.sleep"),
            mock.patch("chat.providers.generate_gemini_reply") as gemini_reply,
        ):
            response = self.post_json({"message": "Question", "provider": "gemini"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["error"],
            "The AI tutor is busy right now. Please try again in a moment.",
        )
        gemini_reply.assert_not_called()

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=True,
        CHAT_AI_PROVIDER="groq",
        GEMINI_TIMEOUT_SECONDS=25,
        GEMINI_503_RETRIES=0,
        GEMINI_THINKING_LEVEL=None,
        GEMINI_THINKING_BUDGET=None,
    )
    def test_both_provider_failures_return_friendly_error_without_using_slot(self):
        with (
            mock.patch(
                "requests.post",
                side_effect=[
                    groq_response({}, 500),
                    groq_response({}, 500),
                    groq_response({}, 500),
                    groq_response({}, 503),
                ],
            ),
            mock.patch("core.ai.groq_transport.time.sleep"),
            mock.patch("chat.gemini.time.sleep"),
        ):
            response = self.post_json({"message": "Question"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["error"],
            "The AI tutor is busy right now. Please try again in a moment.",
        )
        self.assertNotContains(response, "Groq")
        self.assertNotContains(response, "Gemini")
        self.assertEqual(ChatMessage.objects.count(), 0)
        self.assertEqual(ChatSession.objects.count(), 0)

    @override_settings(
        GROQ_API_KEY="groq-key",
        GEMINI_API_KEY="gemini-key",
        CHAT_AI_FALLBACK_FROM_GROQ=True,
        CHAT_AI_PROVIDER="groq",
        CHAT_DAILY_LIMIT=1,
        GEMINI_TIMEOUT_SECONDS=25,
        GEMINI_503_RETRIES=0,
        GEMINI_THINKING_LEVEL=None,
        GEMINI_THINKING_BUDGET=None,
    )
    def test_fallback_reply_consumes_one_daily_slot(self):
        backup = groq_response({
            "candidates": [{"content": {"parts": [{"text": "Backup answer"}]}}],
        })
        with (
            mock.patch(
                "requests.post",
                side_effect=[
                    groq_response({}, 429),
                    groq_response({}, 429),
                    groq_response({}, 429),
                    backup,
                ],
            ),
            mock.patch("core.ai.groq_transport.time.sleep"),
            mock.patch("chat.gemini.time.sleep"),
        ):
            response = self.post_json({"message": "Question", "provider": "gemini"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("provider_used", response.json())
        self.assertNotIn("fallback_from", response.json())
        self.assertEqual(ChatMessage.objects.filter(role="user").count(), 1)
        self.assertEqual(ChatMessage.objects.get(role="assistant").provider, "gemini")
        self.assertEqual(ChatMessage.objects.get(role="assistant").model, "backup-model")

        limited = self.post_json({"message": "One more", "provider": "gemini"})
        self.assertEqual(limited.status_code, 429)
