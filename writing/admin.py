from django import forms
from django.contrib import admin
from django.shortcuts import resolve_url

from .models import WritingAttempt, WritingEvaluation, WritingResponse, WritingScore, WritingTask, WritingTest


class WritingTaskInline(admin.TabularInline):
    model = WritingTask
    extra = 0
    fields = ("task_number", "instructions", "prompt_text", "image", "image_alt", "min_words", "suggested_minutes")


@admin.register(WritingTest)
class WritingTestAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "duration_minutes", "is_published", "source_name")
    list_filter = ("is_published", "module")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [WritingTaskInline]


@admin.register(WritingTask)
class WritingTaskAdmin(admin.ModelAdmin):
    list_display = ("test", "task_number", "min_words", "suggested_minutes")
    list_filter = ("test", "task_number")


class WritingScoreInline(admin.StackedInline):
    model = WritingScore
    extra = 0
    fields = ("criterion_1", "criterion_2", "criterion_3", "criterion_4", "feedback", "scored_by", "scored_at")


@admin.register(WritingResponse)
class WritingResponseAdmin(admin.ModelAdmin):
    list_display = ("attempt", "task", "word_count", "updated_at")
    inlines = [WritingScoreInline]
    readonly_fields = ("word_count", "updated_at")


@admin.register(WritingAttempt)
class WritingAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "test", "status", "mode", "started_at", "submitted_at", "preview")
    list_filter = ("test", "status", "mode")
    readonly_fields = ("responses_display", "preview")

    def responses_display(self, obj):
        if not obj.pk:
            return "-"
        responses = obj.responses.select_related("task").all()
        if not responses:
            return "No responses yet."
        items = [
            f"<li><strong>Task {r.task.task_number}</strong> — {r.word_count} words</li>"
            for r in responses
        ]
        return "<ul>" + "".join(items) + "</ul>"

    responses_display.allow_tags = True
    responses_display.short_description = "Responses"

    def preview(self, obj):
        if not obj.pk:
            return "-"
        href = resolve_url("writing:attempt_preview", obj.pk)
        return f'<a href="{href}" target="_blank">Preview</a>'

    preview.allow_tags = True
    preview.short_description = "Preview"


@admin.register(WritingEvaluation)
class WritingEvaluationAdmin(admin.ModelAdmin):
    list_display = ("response", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("response__attempt__user__username", "response__attempt__test__title")
    readonly_fields = ("response", "request_hash", "status", "result", "error_message", "created_at")
