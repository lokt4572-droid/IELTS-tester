import json
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from writing.evaluation_service import (
    EvaluationServiceError,
    MINIMUM_EVALUATION_WORDS,
    TOO_SHORT_ERROR,
    evaluate_writing_response,
    validate_language,
)
from writing.models import WritingAttempt
from writing.scoring import count_words


class Command(BaseCommand):
    help = "Evaluate submitted writing responses for an attempt."

    def add_arguments(self, parser):
        parser.add_argument("attempt_id", type=int)
        parser.add_argument("--task", type=int, choices=(1, 2))
        parser.add_argument("--language", choices=("en", "ru", "tg"), default="en")
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Print Groq response diagnostics when evaluation validation fails.",
        )

    def handle(self, *args, **options):
        try:
            language = validate_language(options["language"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        attempt = (
            WritingAttempt.objects.select_related("test")
            .prefetch_related("responses__task")
            .filter(pk=options["attempt_id"])
            .first()
        )
        if attempt is None:
            raise CommandError(f"Writing attempt {options['attempt_id']} was not found.")
        if attempt.status not in {"submitted", "expired"}:
            raise CommandError("The attempt must be submitted or expired before evaluation.")

        responses = attempt.responses.select_related("task").all()
        if options["task"] is not None:
            responses = responses.filter(task__task_number=options["task"])
        responses = list(responses.order_by("task__task_number"))
        if options["task"] is None:
            responses = [response for response in responses if response.text.strip()]
        if not responses:
            raise CommandError("No non-empty response was found for the requested task.")
        if any(
            count_words(response.text) < MINIMUM_EVALUATION_WORDS
            for response in responses
        ):
            raise CommandError(TOO_SHORT_ERROR)

        for response in responses:
            started = time.monotonic()
            try:
                result = evaluate_writing_response(
                    response,
                    language,
                    debug=options["debug"],
                )
            except EvaluationServiceError as exc:
                if options["debug"] and exc.validation_error:
                    diagnostics = exc.diagnostics
                    if diagnostics is not None:
                        api_key = settings.GROQ_API_KEY
                        model_content = diagnostics.content
                        model_reasoning = diagnostics.reasoning
                        if api_key:
                            model_content = model_content.replace(api_key, "[REDACTED]")
                            model_reasoning = model_reasoning.replace(api_key, "[REDACTED]")
                        self.stderr.write(f"Model: {diagnostics.model}")
                        self.stderr.write(f"HTTP status: {diagnostics.status_code}")
                        self.stderr.write(f"finish_reason: {diagnostics.finish_reason}")
                        if diagnostics.usage is not None:
                            self.stderr.write(
                                "Token usage: "
                                + json.dumps(diagnostics.usage, ensure_ascii=False)
                            )
                        self.stderr.write(
                            "Model content (first 2000 characters):\n"
                            + model_content[:2000]
                        )
                        self.stderr.write(
                            "Model reasoning (first 1000 characters):\n"
                            + model_reasoning[:1000]
                        )
                    self.stderr.write(
                        f"Validation error: {exc.validation_error}"
                    )
                raise CommandError(
                    f"Task {response.task.task_number} evaluation failed: {exc}"
                ) from exc
            latency_ms = round((time.monotonic() - started) * 1000)
            evaluation = result["evaluation"]
            overall_band = result["overall_band_estimate"]
            overall_label = (
                f" · overall Writing band {overall_band:.1f}"
                if overall_band is not None
                else ""
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Task {response.task.task_number} · estimated band "
                    f"{evaluation['task_band_estimate']:.1f} · {latency_ms} ms"
                    f"{overall_label}"
                    f"{' · cached' if result['cached'] else ''}"
                )
            )
            self.stdout.write(json.dumps(evaluation, ensure_ascii=False, indent=2))
