from django.contrib import admin

from .models import (
    ListeningAnswer,
    ListeningAttempt,
    ListeningGroup,
    ListeningQuestion,
    ListeningSection,
    ListeningTest,
)


class ListeningSectionInline(admin.TabularInline):
    model = ListeningSection
    extra = 0
    fields = (
        "number",
        "title",
        "context",
        "audio",
        "audio_seconds",
        "preview_seconds",
        "check_seconds",
        "image",
    )
    show_change_link = True


class ListeningGroupInline(admin.TabularInline):
    model = ListeningGroup
    extra = 0
    fields = ("order", "qtype", "instruction", "text", "choose")
    show_change_link = True


class ListeningQuestionInline(admin.TabularInline):
    model = ListeningQuestion
    extra = 0
    fields = ("number", "text", "answer", "options", "explanation")


class ListeningAnswerInline(admin.TabularInline):
    model = ListeningAnswer
    extra = 0
    fields = ("question_number", "value", "is_correct")
    readonly_fields = ("question_number", "value", "is_correct")
    can_delete = False


@admin.register(ListeningTest)
class ListeningTestAdmin(admin.ModelAdmin):
    list_display = ("title", "duration_minutes", "is_published", "source_name")
    list_filter = ("is_published",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ListeningSectionInline]


@admin.register(ListeningSection)
class ListeningSectionAdmin(admin.ModelAdmin):
    list_display = ("test", "number", "title", "audio_seconds")
    list_filter = ("test",)
    inlines = [ListeningGroupInline]


@admin.register(ListeningGroup)
class ListeningGroupAdmin(admin.ModelAdmin):
    list_display = ("section", "qtype", "order")
    list_filter = ("section__test", "qtype")
    inlines = [ListeningQuestionInline]


@admin.register(ListeningQuestion)
class ListeningQuestionAdmin(admin.ModelAdmin):
    list_display = ("test", "number", "group", "text")
    list_filter = ("test", "group__qtype")
    search_fields = ("text", "answer")


@admin.register(ListeningAttempt)
class ListeningAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "test",
        "mode",
        "status",
        "current_section",
        "raw_score",
        "band",
        "started_at",
        "submitted_at",
    )
    list_filter = ("test", "mode", "status")
    readonly_fields = ("section_started_at",)
    inlines = [ListeningAnswerInline]


@admin.register(ListeningAnswer)
class ListeningAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question_number", "value", "is_correct")
    list_filter = ("is_correct",)
