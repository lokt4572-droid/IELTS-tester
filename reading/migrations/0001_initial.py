import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingTest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("slug", models.SlugField(max_length=120, unique=True)),
                ("module", models.CharField(choices=[("academic", "Academic"), ("general", "General Training")], default="academic", max_length=10)),
                ("description", models.TextField(blank=True)),
                ("duration_minutes", models.PositiveIntegerField(default=60)),
                ("source_name", models.CharField(blank=True, help_text="Where this test comes from.", max_length=200)),
                ("source_url", models.URLField(blank=True)),
                ("license_note", models.CharField(blank=True, help_text="Why you are allowed to use it.", max_length=300)),
                ("is_published", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["title"]},
        ),
        migrations.CreateModel(
            name="Passage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(default=1)),
                ("title", models.CharField(max_length=200)),
                ("subtitle", models.CharField(blank=True, max_length=300)),
                ("text", models.TextField(help_text="Separate paragraphs with a blank line. Start a paragraph with [A], [B]... to label it.")),
                ("test", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="passages", to="reading.readingtest")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="QuestionGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(default=1)),
                ("qtype", models.CharField(choices=[("tfng", "True / False / Not Given"), ("ynng", "Yes / No / Not Given"), ("mcq", "Multiple choice"), ("matching", "Matching"), ("completion", "Sentence / note completion"), ("short", "Short answer")], max_length=12)),
                ("instruction", models.TextField(blank=True)),
                ("options", models.JSONField(blank=True, default=list, help_text='Matching only: [{"key": "A", "text": "..."}]')),
                ("passage", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="groups", to="reading.passage")),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="Question",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField()),
                ("text", models.TextField(help_text="For gap-fill, mark the blank with ____")),
                ("options", models.JSONField(blank=True, default=list, help_text='Multiple choice only: [{"key": "A", "text": "..."}]')),
                ("answer", models.CharField(help_text="Alternatives separated by |", max_length=255)),
                ("explanation", models.TextField(blank=True)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="questions", to="reading.questiongroup")),
            ],
            options={"ordering": ["number", "id"]},
        ),
        migrations.CreateModel(
            name="Attempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("answers", models.JSONField(blank=True, default=dict)),
                ("score", models.PositiveIntegerField(default=0)),
                ("total", models.PositiveIntegerField(default=0)),
                ("band", models.DecimalField(blank=True, decimal_places=1, max_digits=3, null=True)),
                ("seconds_spent", models.PositiveIntegerField(default=0)),
                ("test", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="reading.readingtest")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reading_attempts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-started_at"]},
        ),
    ]
