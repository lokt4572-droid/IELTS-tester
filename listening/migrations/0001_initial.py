import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ListeningTest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("description", models.TextField(blank=True)),
                ("duration_minutes", models.PositiveIntegerField(default=30)),
                ("review_seconds", models.PositiveIntegerField(default=120)),
                ("source_name", models.CharField(blank=True, max_length=200)),
                ("source_url", models.URLField(blank=True)),
                ("license_note", models.CharField(blank=True, max_length=300)),
                ("is_published", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["title"]},
        ),
        migrations.CreateModel(
            name="ListeningAttempt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[("exam", "Exam"), ("practice", "Practice")],
                        default="exam",
                        max_length=8,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("in_progress", "In progress"),
                            ("submitted", "Submitted"),
                            ("expired", "Expired"),
                        ],
                        default="in_progress",
                        max_length=12,
                    ),
                ),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("current_section", models.PositiveSmallIntegerField(default=1)),
                ("section_started_at", models.JSONField(blank=True, default=dict)),
                ("raw_score", models.PositiveSmallIntegerField(default=0)),
                (
                    "band",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=3,
                        null=True,
                    ),
                ),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempts",
                        to="listening.listeningtest",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="listening_attempts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="ListeningSection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("number", models.PositiveSmallIntegerField()),
                ("title", models.CharField(max_length=200)),
                ("context", models.TextField(blank=True)),
                ("audio", models.FileField(upload_to="listening/audio/")),
                ("audio_seconds", models.PositiveIntegerField()),
                ("preview_seconds", models.PositiveIntegerField(default=30)),
                ("check_seconds", models.PositiveIntegerField(default=30)),
                ("transcript", models.TextField(blank=True)),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="listening/images/",
                    ),
                ),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sections",
                        to="listening.listeningtest",
                    ),
                ),
            ],
            options={"ordering": ["number"]},
        ),
        migrations.CreateModel(
            name="ListeningGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("order", models.PositiveIntegerField(default=1)),
                (
                    "qtype",
                    models.CharField(
                        choices=[
                            ("mcq", "Multiple choice"),
                            ("mcq_multi", "Multiple choice (choose multiple)"),
                            ("matching", "Matching"),
                            ("completion", "Completion"),
                            ("short", "Short answer"),
                            ("diagram_label", "Diagram label"),
                        ],
                        max_length=20,
                    ),
                ),
                ("instruction", models.TextField(blank=True)),
                ("text", models.TextField(blank=True)),
                ("options", models.JSONField(blank=True, default=list)),
                ("max_words", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("choose", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="listening/images/",
                    ),
                ),
                ("multi_question_numbers", models.JSONField(blank=True, default=list)),
                ("multi_answers", models.JSONField(blank=True, default=list)),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="groups",
                        to="listening.listeningsection",
                    ),
                ),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="ListeningQuestion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("number", models.PositiveSmallIntegerField()),
                ("text", models.TextField()),
                ("answer", models.CharField(max_length=255)),
                ("options", models.JSONField(blank=True, default=list)),
                ("explanation", models.TextField(blank=True)),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="questions",
                        to="listening.listeninggroup",
                    ),
                ),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="questions",
                        to="listening.listeningtest",
                    ),
                ),
            ],
            options={"ordering": ["number"]},
        ),
        migrations.CreateModel(
            name="ListeningAnswer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("question_number", models.PositiveSmallIntegerField()),
                ("value", models.CharField(blank=True, max_length=255)),
                ("is_correct", models.BooleanField(blank=True, null=True)),
                (
                    "attempt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answers",
                        to="listening.listeningattempt",
                    ),
                ),
            ],
            options={"ordering": ["question_number"]},
        ),
        migrations.AddConstraint(
            model_name="listeningsection",
            constraint=models.UniqueConstraint(
                fields=("test", "number"),
                name="unique_listening_section_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="listeningsection",
            constraint=models.CheckConstraint(
                condition=Q(number__gte=1, number__lte=4),
                name="listening_section_number_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="listeningquestion",
            constraint=models.UniqueConstraint(
                fields=("test", "number"),
                name="unique_listening_question_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="listeningquestion",
            constraint=models.CheckConstraint(
                condition=Q(number__gte=1, number__lte=40),
                name="listening_question_number_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="listeningattempt",
            constraint=models.CheckConstraint(
                condition=Q(current_section__gte=1, current_section__lte=4),
                name="listening_attempt_section_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="listeninganswer",
            constraint=models.UniqueConstraint(
                fields=("attempt", "question_number"),
                name="unique_listening_attempt_answer",
            ),
        ),
    ]
