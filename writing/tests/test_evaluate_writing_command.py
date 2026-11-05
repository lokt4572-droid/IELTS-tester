import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from writing.evaluation_service import EvaluationServiceError
from writing.groq import GroqResponse
from writing.models import WritingAttempt, WritingResponse, WritingTask, WritingTest


class EvaluateWritingCommandTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="command-writer", password="password")
        test = WritingTest.objects.create(title="Command test", slug="command-test")
        attempt = WritingAttempt.objects.create(user=user, test=test, status="submitted")
        task1 = WritingTask.objects.create(test=test, task_number=1, prompt_text="Task one.")
        task2 = WritingTask.objects.create(test=test, task_number=2, prompt_text="Task two.")
        self.attempt = attempt
        self.response1 = WritingResponse.objects.create(
            attempt=attempt,
            task=task1,
            text=(
                "First response contains enough words to reach the required "
                "minimum, and describes its main point in a clear sentence today."
            ),
        )
        self.response2 = WritingResponse.objects.create(
            attempt=attempt,
            task=task2,
            text=(
                "Second response also contains enough words to reach the "
                "minimum, and explains the writer's argument in a clear way today."
            ),
        )

    @mock.patch("writing.management.commands.evaluate_writing.evaluate_writing_response")
    def test_command_evaluates_both_tasks_and_prints_band_latency_and_result(self, evaluate):
        evaluate.return_value = {
            "evaluation": {"task_band_estimate": 6.5, "overall": {"summary": "Good."}},
            "cached": False,
            "remaining_today": 2,
            "latency_ms": 12,
            "overall_band_estimate": 6.5,
        }
        output = io.StringIO()

        call_command("evaluate_writing", str(self.attempt.pk), "--language", "tg", stdout=output)

        self.assertEqual(evaluate.call_count, 2)
        self.assertEqual(evaluate.call_args_list[0].args[0].pk, self.response1.pk)
        self.assertEqual(evaluate.call_args_list[0].args[1], "tg")
        self.assertEqual(evaluate.call_args_list[1].args[0].pk, self.response2.pk)
        self.assertIn("estimated band 6.5", output.getvalue())
        self.assertIn("overall Writing band 6.5", output.getvalue())
        self.assertIn("ms", output.getvalue())
        self.assertIn('"summary": "Good."', output.getvalue())

    @mock.patch("writing.management.commands.evaluate_writing.evaluate_writing_response")
    def test_task_option_limits_evaluation_to_selected_task(self, evaluate):
        evaluate.return_value = {
            "evaluation": {"task_band_estimate": 7.0},
            "cached": True,
            "remaining_today": 2,
            "latency_ms": 0,
            "overall_band_estimate": None,
        }

        call_command("evaluate_writing", str(self.attempt.pk), "--task", "2")

        evaluate.assert_called_once()
        self.assertEqual(evaluate.call_args.args[0].pk, self.response2.pk)

    def test_command_requires_a_submitted_attempt(self):
        self.attempt.status = "in_progress"
        self.attempt.save(update_fields=["status"])
        with self.assertRaises(CommandError):
            call_command("evaluate_writing", str(self.attempt.pk))

    @mock.patch("writing.management.commands.evaluate_writing.evaluate_writing_response")
    def test_command_reports_too_short_text_without_evaluating(self, evaluate):
        self.response1.text = "This response has fewer than twenty words and must not be evaluated by Groq."
        self.response1.save()

        with self.assertRaisesRegex(
            CommandError,
            "Text is too short to evaluate \\(minimum 20 words\\)",
        ):
            call_command(
                "evaluate_writing",
                str(self.attempt.pk),
                "--task",
                "1",
            )

        evaluate.assert_not_called()

    @mock.patch("writing.management.commands.evaluate_writing.evaluate_writing_response")
    @override_settings(GROQ_API_KEY="COMMAND_TEST_SECRET")
    def test_debug_prints_validation_reason_and_provider_diagnostics(self, evaluate):
        reply = "C" * 100 + "COMMAND_TEST_SECRET" + "C" * 3000
        evaluate.side_effect = EvaluationServiceError(
            "The Writing evaluator returned an invalid assessment.",
            validation_error="criteria.lexical_resource.band must be between 0 and 9 in half-band steps.",
            diagnostics=GroqResponse(
                content=reply,
                model="openai/gpt-oss-20b",
                status_code=200,
                finish_reason="stop",
                usage={"completion_tokens": 25},
                reasoning="COMMAND_TEST_SECRET" + "reasoning " * 200,
            ),
        )
        stderr = io.StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "evaluate_writing",
                str(self.attempt.pk),
                "--task",
                "1",
                "--debug",
                stderr=stderr,
            )

        output = stderr.getvalue()
        self.assertIn("Model: openai/gpt-oss-20b", output)
        self.assertIn("HTTP status: 200", output)
        self.assertIn("finish_reason: stop", output)
        self.assertIn('"completion_tokens": 25', output)
        self.assertIn(
            "criteria.lexical_resource.band must be between 0 and 9 in half-band steps.",
            output,
        )
        content_label = "Model content (first 2000 characters):\n"
        reasoning_label = "Model reasoning (first 1000 characters):\n"
        self.assertIn(content_label, output)
        self.assertIn(reasoning_label, output)
        model_content = output.split(content_label, 1)[1].split(
            "\n" + reasoning_label, 1
        )[0]
        expected_content = "C" * 100 + "[REDACTED]" + "C" * (
            2000 - 100 - len("[REDACTED]")
        )
        self.assertEqual(model_content, expected_content)
        self.assertIn("[REDACTED]reasoning", output)
        self.assertNotIn("COMMAND_TEST_SECRET", output)
        self.assertNotIn("api_key", output.lower())
        evaluate.assert_called_once()
        self.assertTrue(evaluate.call_args.kwargs["debug"])

    @mock.patch("writing.management.commands.evaluate_writing.evaluate_writing_response")
    @override_settings(GROQ_API_KEY="COMMAND_TEST_SECRET")
    def test_debug_prints_content_label_when_model_has_no_reasoning(self, evaluate):
        evaluate.side_effect = EvaluationServiceError(
            "The Writing evaluator returned an invalid assessment.",
            validation_error="The JSON object is missing criteria.",
            diagnostics=GroqResponse(
                content='{"overall": {}}',
                model="openai/gpt-oss-20b",
                status_code=200,
                finish_reason="stop",
                usage=None,
                reasoning="",
            ),
        )
        stderr = io.StringIO()

        with self.assertRaises(CommandError):
            call_command(
                "evaluate_writing",
                str(self.attempt.pk),
                "--task",
                "1",
                "--debug",
                stderr=stderr,
            )

        output = stderr.getvalue()
        self.assertIn("Model content (first 2000 characters):", output)
        self.assertIn('{"overall": {}}', output)
        self.assertIn("Model reasoning (first 1000 characters):", output)
        self.assertNotIn("COMMAND_TEST_SECRET", output)
        evaluate.assert_called_once()
