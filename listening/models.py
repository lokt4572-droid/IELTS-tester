from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


QUESTION_TYPE_CHOICES = [
    ("mcq", "Multiple choice"),
    ("mcq_multi", "Multiple choice (choose multiple)"),
    ("matching", "Matching"),
    ("completion", "Completion"),
    ("short", "Short answer"),
    ("diagram_label", "Diagram label"),
]


class ListeningTest(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
    review_seconds = models.PositiveIntegerField(default=120)
    source_name = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(blank=True)
    license_note = models.CharField(max_length=300, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def question_count(self):
        return self.questions.count()


class ListeningSection(models.Model):
    test = models.ForeignKey(
        ListeningTest,
        on_delete=models.CASCADE,
        related_name="sections",
    )
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    context = models.TextField(blank=True)
    audio = models.FileField(upload_to="listening/audio/")
    audio_seconds = models.PositiveIntegerField()
    preview_seconds = models.PositiveIntegerField(default=30)
    check_seconds = models.PositiveIntegerField(default=30)
    transcript = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="listening/images/",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["test", "number"],
                name="unique_listening_section_number",
            ),
            models.CheckConstraint(
                condition=Q(number__gte=1, number__lte=4),
                name="listening_section_number_range",
            ),
        ]

    def __str__(self):
        return f"{self.test.title} – Section {self.number}"


class ListeningGroup(models.Model):
    section = models.ForeignKey(
        ListeningSection,
        on_delete=models.CASCADE,
        related_name="groups",
    )
    order = models.PositiveIntegerField(default=1)
    qtype = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES)
    instruction = models.TextField(blank=True)
    text = models.TextField(blank=True)
    options = models.JSONField(default=list, blank=True)
    max_words = models.PositiveSmallIntegerField(null=True, blank=True)
    choose = models.PositiveSmallIntegerField(null=True, blank=True)
    image = models.ImageField(
        upload_to="listening/images/",
        blank=True,
        null=True,
    )
    multi_question_numbers = models.JSONField(
        default=list,
        blank=True,
        help_text="Question numbers for a shared multi-select prompt.",
    )
    multi_answers = models.JSONField(
        default=list,
        blank=True,
        help_text="Correct option letters, in the same order as the question numbers.",
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.section}: {self.get_qtype_display()}"


class ListeningQuestion(models.Model):
    test = models.ForeignKey(
        ListeningTest,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    group = models.ForeignKey(
        ListeningGroup,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    number = models.PositiveSmallIntegerField()
    text = models.TextField()
    answer = models.CharField(max_length=255)
    options = models.JSONField(default=list, blank=True)
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["test", "number"],
                name="unique_listening_question_number",
            ),
            models.CheckConstraint(
                condition=Q(number__gte=1, number__lte=40),
                name="listening_question_number_range",
            ),
        ]

    def clean(self):
        super().clean()
        if self.group_id and self.test_id:
            section_test_id = self.group.section.test_id
            if self.test_id != section_test_id:
                raise ValidationError(
                    {"test": "The question and its group must belong to the same test."}
                )

    def __str__(self):
        return f"Q{self.number}"


class ListeningAttempt(models.Model):
    MODE_CHOICES = [("exam", "Exam"), ("practice", "Practice")]
    STATUS_CHOICES = [
        ("in_progress", "In progress"),
        ("submitted", "Submitted"),
        ("expired", "Expired"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listening_attempts",
    )
    test = models.ForeignKey(
        ListeningTest,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default="exam")
    exam_started_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default="in_progress",
    )
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    current_section = models.PositiveSmallIntegerField(default=1)
    section_started_at = models.JSONField(default=dict, blank=True)
    raw_score = models.PositiveSmallIntegerField(default=0)
    band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(current_section__gte=1, current_section__lte=4),
                name="listening_attempt_section_range",
            )
        ]

    def __str__(self):
        return f"{self.user} – {self.test} ({self.mode})"


class ListeningAnswer(models.Model):
    attempt = models.ForeignKey(
        ListeningAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question_number = models.PositiveSmallIntegerField()
    value = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["question_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question_number"],
                name="unique_listening_attempt_answer",
            )
        ]

    def __str__(self):
        return f"{self.attempt}: Q{self.question_number}"
