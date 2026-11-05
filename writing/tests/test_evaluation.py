import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from writing.evaluation_validation import (
    VALIDATION_VERSION,
    EvaluationValidationError,
    validate_evaluation,
)
from writing import evaluation_service
from writing.groq import GroqError
from writing.models import (
    WritingAttempt,
    WritingEvaluation,
    WritingResponse,
    WritingTask,
    WritingTest,
)


def valid_evaluation():
    criteria = {
        "task_achievement_or_response": 6.0,
        "coherence_and_cohesion": 6.5,
        "lexical_resource": 6.0,
        "grammatical_range_and_accuracy": 6.0,
    }
    return {
        "criteria": {
            name: {
                "band": band,
                "comment": f"Evidence-based comment for {name}.",
                "evidence": ["The chart shows"],
            }
            for name, band in criteria.items()
        },
        "overall": {
            "strengths": ["The position is clear."],
            "weaknesses": ["Some details need support."],
            "corrections": [{
                "original": "the chart shows",
                "improved": "The chart illustrates",
                "reason": "Use a more precise reporting verb.",
            }],
            "next_steps": ["Develop each main point."],
            "summary": "A clear response with areas to develop.",
        },
    }


@override_settings(
    GROQ_API_KEY="test-key",
    GROQ_MODEL="test-model",
    GROQ_FALLBACK_MODEL="test-fallback",
    GROQ_EVALUATIONS_DAILY_LIMIT=3,
)
class EvaluationEndpointTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="writer", password="password")
        self.other_user = user_model.objects.create_user(username="other", password="password")
        self.test = WritingTest.objects.create(
            title="Writing test",
            slug="writing-test",
            is_published=True,
        )
        self.task = WritingTask.objects.create(
            test=self.test,
            task_number=1,
            prompt_text="Describe the chart.",
        )
        self.attempt = WritingAttempt.objects.create(
            user=self.user,
            test=self.test,
            status="submitted",
        )
        self.response = WritingResponse.objects.create(
            attempt=self.attempt,
            task=self.task,
            text=(
                "The chart shows several changes over the observed period, while "
                "the figures for the remaining categories continued to rise gradually."
            ),
        )
        self.url = reverse("writing:evaluate", args=[self.attempt.pk])
        self.client.force_login(self.user)

    def post_evaluation(self, task_number=1, language="en"):
        payload = {"task_number": task_number}
        if language is not None:
            payload["language"] = language
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_result_page_hides_ai_section_for_unfinished_attempt(self):
        self.attempt.status = "in_progress"
        self.attempt.save(update_fields=["status"])

        response = self.client.get(
            reverse("writing:result", args=[self.attempt.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "AI estimate (not an official IELTS score)")

    @override_settings(GROQ_API_KEY="")
    def test_result_page_hides_ai_section_when_evaluation_is_disabled(self):
        response = self.client.get(reverse("writing:result", args=[self.attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "AI estimate (not an official IELTS score)")
        self.assertNotContains(response, "Get AI feedback")

    @mock.patch("writing.views.evaluate_writing_response")
    def test_result_page_loads_existing_evaluation_data_and_empty_strengths(self, evaluate):
        evaluation = valid_evaluation()
        evaluation["overall"]["strengths"] = []
        WritingEvaluation.objects.create(
            response=self.response,
            request_hash="existing-result-hash",
            status="completed",
            result=evaluation,
        )

        response = self.client.get(reverse("writing:result", args=[self.attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "wr-existing-evaluation-1")
        self.assertContains(response, '"strengths": []')
        self.assertNotContains(response, "Get AI feedback")
        evaluate.assert_not_called()

    def test_result_page_escapes_html_in_stored_ai_output(self):
        evaluation = valid_evaluation()
        evaluation["overall"]["summary"] = "<script>alert('xss')</script>"
        evaluation["criteria"]["lexical_resource"]["evidence"] = [
            "<img src=x onerror=alert(1)>"
        ]
        WritingEvaluation.objects.create(
            response=self.response,
            request_hash="escaped-result-hash",
            status="completed",
            result=evaluation,
        )

        response = self.client.get(reverse("writing:result", args=[self.attempt.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert")
        self.assertNotContains(response, "<img src=x")
        self.assertContains(response, "\\u003Cscript\\u003E")
        self.assertContains(response, "\\u003Cimg")

    @mock.patch("writing.evaluation_service.evaluate_response", return_value=json.dumps(valid_evaluation()))
    def test_success_caches_identical_evaluation_and_does_not_charge_again(self, evaluate):
        first = self.post_evaluation()
        second = self.post_evaluation()

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["cached"])
        self.assertEqual(first.json()["remaining_today"], 2)
        self.assertGreaterEqual(first.json()["latency_ms"], 0)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["cached"])
        self.assertEqual(second.json()["remaining_today"], 2)
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(
            WritingEvaluation.objects.filter(response=self.response, status="completed").count(),
            1,
        )

    @mock.patch("writing.evaluation_service.evaluate_response", return_value=json.dumps(valid_evaluation()))
    def test_language_is_passed_to_prompt_and_part_of_cache_key(self, evaluate):
        english = self.post_evaluation(language="en")
        russian = self.post_evaluation(language="ru")
        tajik = self.post_evaluation(language="tg")

        self.assertEqual(english.status_code, 200)
        self.assertEqual(russian.status_code, 200)
        self.assertEqual(tajik.status_code, 200)
        self.assertFalse(russian.json()["cached"])
        self.assertFalse(tajik.json()["cached"])
        self.assertEqual(evaluate.call_count, 3)
        self.assertEqual(evaluate.call_args.kwargs["language"], "tg")

    @mock.patch("writing.evaluation_service.evaluate_response", return_value=json.dumps(valid_evaluation()))
    def test_endpoint_defaults_language_to_english(self, evaluate):
        result = self.post_evaluation(language=None)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(evaluate.call_args.kwargs["language"], "en")

    @mock.patch("writing.evaluation_service.evaluate_response", return_value=json.dumps(valid_evaluation()))
    def test_changed_response_creates_a_fresh_evaluation(self, evaluate):
        self.post_evaluation()
        self.response.text = (
            "The chart shows a different response with several categories that "
            "changed at different rates across the full observed period overall."
        )
        self.response.save()
        result = self.post_evaluation()

        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["cached"])
        self.assertEqual(evaluate.call_count, 2)

    def test_cache_key_changes_with_validation_version(self):
        original_hash = evaluation_service.evaluation_request_hash(self.response, "en")

        with mock.patch(
            "writing.evaluation_service.VALIDATION_VERSION",
            "validation-version-test",
        ):
            changed_hash = evaluation_service.evaluation_request_hash(self.response, "en")

        self.assertNotEqual(original_hash, changed_hash)

    def test_cache_key_changes_with_validation_version(self):
        first_hash = evaluation_service.evaluation_request_hash(self.response, "en")
        with mock.patch(
            "writing.evaluation_service.VALIDATION_VERSION",
            VALIDATION_VERSION + "-next",
        ):
            second_hash = evaluation_service.evaluation_request_hash(self.response, "en")

        self.assertNotEqual(first_hash, second_hash)

    @mock.patch("writing.evaluation_service.evaluate_response")
    def test_too_short_response_does_not_call_groq_or_create_evaluation(self, evaluate):
        self.response.text = "This response has only nineteen words and should not be sent to the Groq provider for evaluation at all."
        self.response.save()
        self.assertEqual(len(self.response.text.split()), 19)

        result = self.post_evaluation()

        self.assertEqual(result.status_code, 400)
        self.assertEqual(
            result.json(),
            {
                "error": "Text is too short to evaluate (minimum 20 words)",
                "too_short": True,
            },
        )
        evaluate.assert_not_called()
        self.assertEqual(WritingEvaluation.objects.count(), 0)
        self.assertEqual(
            WritingEvaluation.objects.filter(status="completed").count(),
            0,
        )

    @mock.patch(
        "writing.evaluation_service.evaluate_response",
        side_effect=GroqError("Provider unavailable"),
    )
    def test_provider_failure_does_not_consume_daily_limit(self, evaluate):
        result = self.post_evaluation()

        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json()["remaining_today"], 3)
        self.assertEqual(WritingEvaluation.objects.filter(status="completed").count(), 0)

    @mock.patch(
        "writing.evaluation_service.evaluate_response",
        side_effect=GroqError(
            "The model ran out of tokens; increase GROQ_MAX_TOKENS",
            retryable=True,
        ),
    )
    def test_length_finish_reason_failure_does_not_consume_daily_limit(self, evaluate):
        result = self.post_evaluation()

        self.assertEqual(result.status_code, 502)
        self.assertEqual(
            result.json()["error"],
            "The model ran out of tokens; increase GROQ_MAX_TOKENS",
        )
        self.assertEqual(result.json()["remaining_today"], 3)
        failed = WritingEvaluation.objects.get(status="failed")
        self.assertEqual(
            failed.error_message,
            "The model ran out of tokens; increase GROQ_MAX_TOKENS",
        )

    @mock.patch("writing.evaluation_service.evaluate_response", return_value="not JSON")
    def test_invalid_provider_output_does_not_consume_daily_limit(self, evaluate):
        result = self.post_evaluation()

        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json()["remaining_today"], 3)
        failed = WritingEvaluation.objects.get(status="failed")
        self.assertTrue(failed.error_message.startswith("Expecting value"))
        self.assertNotIn("test-key", failed.error_message)

    @mock.patch(
        "writing.evaluation_service.evaluate_response",
        return_value=json.dumps({"criteria": {}, "overall": {}}),
    )
    def test_schema_validation_reason_is_stored_without_using_a_slot(self, evaluate):
        result = self.post_evaluation()

        self.assertEqual(result.status_code, 502)
        self.assertEqual(result.json()["remaining_today"], 3)
        failed = WritingEvaluation.objects.get(status="failed")
        self.assertEqual(
            failed.error_message,
            "Evaluation must include all four IELTS criteria.",
        )

    @mock.patch("writing.evaluation_service.evaluate_response", return_value=json.dumps(valid_evaluation()))
    def test_only_successful_evaluations_count_toward_limit(self, evaluate):
        for index in range(4):
            WritingEvaluation.objects.create(
                response=self.response,
                request_hash=f"failed-{index}",
                status="failed",
            )
        result = self.post_evaluation()

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["remaining_today"], 2)
        evaluate.assert_called_once()

    @mock.patch("writing.evaluation_service.evaluate_response")
    def test_daily_limit_blocks_new_evaluation_after_three_successes(self, evaluate):
        for index in range(3):
            WritingEvaluation.objects.create(
                response=self.response,
                request_hash=f"success-{index}",
                status="completed",
                result=valid_evaluation(),
            )
        result = self.post_evaluation(language="ru")

        self.assertEqual(result.status_code, 429)
        self.assertEqual(result.json()["remaining_today"], 0)
        evaluate.assert_not_called()

    def test_only_owner_can_evaluate_and_attempt_must_be_finished(self):
        self.client.force_login(self.other_user)
        not_found = self.post_evaluation()
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.json(), {"error": "Attempt not found."})

        self.client.force_login(self.user)
        self.attempt.status = "in_progress"
        self.attempt.save(update_fields=["status"])
        self.assertEqual(self.post_evaluation().status_code, 409)

    @mock.patch("writing.evaluation_service.evaluate_response", return_value=json.dumps(valid_evaluation()))
    def test_expired_attempt_can_be_evaluated(self, evaluate):
        self.attempt.status = "expired"
        self.attempt.save(update_fields=["status"])

        result = self.post_evaluation()

        self.assertEqual(result.status_code, 200)
        evaluate.assert_called_once()

    @mock.patch("writing.evaluation_service.evaluate_response")
    def test_overall_writing_band_waits_for_both_tasks_and_uses_server_scoring(self, evaluate):
        task1_data = valid_evaluation()
        task2_data = valid_evaluation()
        for criterion in task1_data["criteria"].values():
            criterion["band"] = 5.5
        for criterion in task2_data["criteria"].values():
            criterion["band"] = 7.0
        evaluate.side_effect = [json.dumps(task1_data), json.dumps(task2_data)]
        task2 = WritingTask.objects.create(
            test=self.test,
            task_number=2,
            prompt_text="Discuss the topic.",
        )
        WritingResponse.objects.create(
            attempt=self.attempt,
            task=task2,
            text=(
                "A second response includes enough words for assessment and "
                "explains the main reasons behind the writer's position clearly "
                "with careful detail."
            ),
        )

        task1_result = self.post_evaluation(task_number=1)
        task2_result = self.post_evaluation(task_number=2)

        self.assertEqual(task1_result.status_code, 200)
        self.assertEqual(task1_result.json()["evaluation"]["task_band_estimate"], 5.5)
        self.assertIsNone(task1_result.json()["overall_band_estimate"])
        self.assertEqual(task2_result.status_code, 200)
        self.assertEqual(task2_result.json()["evaluation"]["task_band_estimate"], 7.0)
        self.assertEqual(task2_result.json()["overall_band_estimate"], 6.5)

    def test_login_is_required(self):
        self.client.logout()
        result = self.post_evaluation()
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.json()["error"], "Authentication is required.")

    def test_json_only_post_and_language_validation(self):
        method_not_allowed = self.client.get(self.url)
        self.assertEqual(method_not_allowed.status_code, 405)
        self.assertEqual(method_not_allowed.json(), {"error": "Method not allowed."})
        self.assertEqual(method_not_allowed["Allow"], "POST")
        self.assertEqual(self.client.post(self.url, {"task_number": 1}).status_code, 415)
        invalid_language = self.client.post(
            self.url,
            data=json.dumps({"task_number": 1, "language": "fr"}),
            content_type="application/json",
        )
        self.assertEqual(invalid_language.status_code, 400)
        invalid_json = self.client.post(self.url, data="{", content_type="application/json")
        self.assertEqual(invalid_json.status_code, 400)

    def test_csrf_protection_is_enabled(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        result = csrf_client.post(
            self.url,
            data=json.dumps({"task_number": 1}),
            content_type="application/json",
        )
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.json(), {"error": "CSRF verification failed."})

    @override_settings(GROQ_API_KEY="")
    def test_missing_key_returns_clear_disabled_response(self):
        result = self.post_evaluation()
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.json()["error"], "The Writing evaluator is not configured.")

    @mock.patch(
        "writing.evaluation_service.evaluate_response",
        side_effect=GroqError("Invalid response"),
    )
    def test_api_key_is_not_in_errors_or_persisted_admin_data(self, evaluate):
        with override_settings(GROQ_API_KEY="SUPER_SECRET_KEY"):
            result = self.post_evaluation()
        self.assertNotIn("SUPER_SECRET_KEY", result.content.decode())
        saved = WritingEvaluation.objects.get(response=self.response)
        self.assertNotIn("SUPER_SECRET_KEY", saved.error_message)
        self.assertNotIn("SUPER_SECRET_KEY", json.dumps(saved.result))
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_staff", "is_superuser"])
        self.client.force_login(self.user)
        admin_response = self.client.get(
            reverse("admin:writing_writingevaluation_change", args=[saved.pk])
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertNotIn("SUPER_SECRET_KEY", admin_response.content.decode())


class EvaluationValidationTests(TestCase):
    def test_valid_payload_is_normalized_to_requested_schema(self):
        result = validate_evaluation(valid_evaluation(), "The chart shows several changes.")
        self.assertEqual(result["task_band_estimate"], 6.0)
        criterion = result["criteria"]["task_achievement_or_response"]
        self.assertEqual(set(criterion), {"band", "comment", "evidence"})
        self.assertEqual(
            set(result["overall"]),
            {"strengths", "weaknesses", "corrections", "next_steps", "summary"},
        )

    def test_empty_strengths_and_weaknesses_are_accepted(self):
        data = valid_evaluation()
        data["overall"]["strengths"] = []
        data["overall"]["weaknesses"] = []

        result = validate_evaluation(data, "The chart shows several changes.")

        self.assertEqual(result["overall"]["strengths"], [])
        self.assertEqual(result["overall"]["weaknesses"], [])

    def test_evidence_quotes_are_canonicalized_with_collapsed_whitespace(self):
        data = valid_evaluation()
        data["criteria"]["lexical_resource"]["evidence"] = [
            " THE   CHART \n shows ",
            "invented quotation",
        ]
        result = validate_evaluation(data, "The\tchart\nshows several changes.")
        self.assertEqual(
            result["criteria"]["lexical_resource"]["evidence"],
            ["The\tchart\nshows"],
        )

    def test_evidence_with_missing_spaces_is_replaced_with_exact_learner_text(self):
        data = valid_evaluation()
        for criterion in data["criteria"].values():
            criterion["evidence"] = ["everyyear", "in2020"]

        result = validate_evaluation(
            data,
            "Prices increased every year, and sales peaked in 2020.",
        )

        for criterion in result["criteria"].values():
            self.assertEqual(criterion["evidence"], ["every year", "in 2020"])

    def test_evidence_case_is_ignored_but_exact_original_case_is_stored(self):
        data = valid_evaluation()
        data["criteria"]["lexical_resource"]["evidence"] = ["THE CHART SHOWS"]

        result = validate_evaluation(data, "The Chart Shows several changes.")

        self.assertEqual(
            result["criteria"]["lexical_resource"]["evidence"],
            ["The Chart Shows"],
        )

    def test_evidence_curly_and_straight_apostrophes_are_equivalent(self):
        data = valid_evaluation()
        for criterion in data["criteria"].values():
            criterion["evidence"] = ["learner's response"]

        result = validate_evaluation(data, "The learner’s response was clear.")

        for criterion in result["criteria"].values():
            self.assertEqual(criterion["evidence"], ["learner’s response"])

    def test_evidence_normalizes_en_and_em_dashes_to_hyphens(self):
        data = valid_evaluation()
        data["criteria"]["lexical_resource"]["evidence"] = ["cost-effective"]

        result = validate_evaluation(data, "The method was cost—effective.")

        self.assertEqual(
            result["criteria"]["lexical_resource"]["evidence"],
            ["cost—effective"],
        )

    def test_unverified_correction_original_is_dropped(self):
        data = valid_evaluation()
        data["overall"]["corrections"].append({
            "original": "This sentence never appeared in the response.",
            "improved": "Suggested text",
            "reason": "It was fabricated.",
        })
        result = validate_evaluation(data, "The chart shows several changes.")
        self.assertEqual(len(result["overall"]["corrections"]), 1)

    def test_correction_original_with_missing_spaces_is_canonicalized(self):
        data = valid_evaluation()
        data["overall"]["corrections"] = [{
            "original": "everyyear",
            "improved": "every year",
            "reason": "Spacing.",
        }]

        result = validate_evaluation(data, "Prices increased every year.")

        self.assertEqual(
            result["overall"]["corrections"],
            [{
                "original": "every year",
                "improved": "every year",
                "reason": "Spacing.",
            }],
        )

    def test_corrections_are_limited_to_five(self):
        data = valid_evaluation()
        data["overall"]["corrections"] = [data["overall"]["corrections"][0]] * 6
        with self.assertRaises(EvaluationValidationError):
            validate_evaluation(data, "The chart shows several changes.")

    def test_computes_task_band_and_rejects_model_supplied_task_band(self):
        data = valid_evaluation()
        for criterion in data["criteria"].values():
            criterion["band"] = 7.0
        result = validate_evaluation(data, "The chart shows several changes.")
        self.assertEqual(result["task_band_estimate"], 7.0)

        data["task_band_estimate"] = 7.0
        with self.assertRaises(EvaluationValidationError):
            validate_evaluation(data, "The chart shows several changes.")

    def test_rejects_invalid_bands(self):
        invalid_band = valid_evaluation()
        invalid_band["criteria"]["lexical_resource"]["band"] = 6.2
        with self.assertRaises(EvaluationValidationError):
            validate_evaluation(invalid_band, "The chart shows several changes.")
