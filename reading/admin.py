import json

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .importer import AlreadyExists, load_test
from .models import Attempt, Passage, Question, QuestionGroup, ReadingTest
from .schema import SchemaError


class ImportForm(forms.Form):
    file = forms.FileField(label="JSON file", help_text="See sample_data/ and the README for the format.")
    replace = forms.BooleanField(required=False, label="Replace a test with the same slug")
    publish = forms.BooleanField(required=False, label="Publish immediately")


class PassageInline(admin.TabularInline):
    model = Passage
    extra = 0
    fields = ("order", "title")
    show_change_link = True


class GroupInline(admin.TabularInline):
    model = QuestionGroup
    extra = 0
    fields = ("order", "qtype", "instruction")
    show_change_link = True


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ("number", "text", "options", "answer", "explanation")


@admin.register(ReadingTest)
class ReadingTestAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "duration_minutes", "is_published", "source_name")
    list_filter = ("is_published", "module")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [PassageInline]
    change_list_template = "admin/reading/readingtest/change_list.html"

    def get_urls(self):
        custom = [path("import-json/", self.admin_site.admin_view(self.import_json_view),
                       name="reading_readingtest_import")]
        return custom + super().get_urls()

    def import_json_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = ImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            try:
                data = json.loads(form.cleaned_data["file"].read().decode("utf-8-sig"))
                imported = 0
                for item in data if isinstance(data, list) else [data]:
                    test = load_test(
                        item,
                        replace=form.cleaned_data["replace"],
                        publish=form.cleaned_data["publish"],
                    )
                    for warning in test.import_warnings:
                        messages.warning(request, warning)
                    imported += 1
                messages.success(request, f"Imported {imported} test(s).")
                return redirect(reverse("admin:reading_readingtest_changelist"))
            except (ValueError, UnicodeDecodeError) as exc:
                if isinstance(exc, SchemaError):
                    for err in exc.errors:
                        messages.error(request, err)
                else:
                    messages.error(request, f"Could not read the file: {exc}")
            except AlreadyExists as exc:
                messages.error(request, str(exc))
        context = {**self.admin_site.each_context(request), "form": form,
                   "opts": self.model._meta, "title": "Import reading test from JSON"}
        return TemplateResponse(request, "admin/reading/import_json.html", context)


@admin.register(Passage)
class PassageAdmin(admin.ModelAdmin):
    list_display = ("title", "test", "order")
    inlines = [GroupInline]


@admin.register(QuestionGroup)
class QuestionGroupAdmin(admin.ModelAdmin):
    list_display = ("__str__", "qtype", "order")
    inlines = [QuestionInline]


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "test", "score", "total", "band", "started_at", "finished_at")
    list_filter = ("test",)
    readonly_fields = ("answers",)
