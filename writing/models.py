from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class WritingTest(models.Model):
    MODULES = [("academic", "Academic"), ("general", "General Training")]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    module = models.CharField(max_length=10, choices=MODULES, default="academic")
    duration_minutes = models.PositiveIntegerField(default=60)
    description = models.TextField(blank=True)
    source_name = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(blank=True)
    license_note = models.CharField(max_length=300, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class WritingTask(models.Model):
    test = models.ForeignKey(WritingTest, on_delete=models.CASCADE, related_name="tasks")
    task_number = models.PositiveSmallIntegerField()
    instructions = models.TextField(blank=True)
    prompt_text = models.TextField()
    image = models.ImageField(upload_to="writing/images/", blank=True, null=True)
    image_alt = models.CharField(max_length=255, blank=True)
    min_words = models.PositiveIntegerField(default=150)
    suggested_minutes = models.PositiveIntegerField(default=20)
    sample_answer = models.TextField(blank=True)
    sample_answer_band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)

    class Meta:
        ordering = ["task_number"]
        constraints = [
            models.UniqueConstraint(fields=["test", "task_number"], name="unique_writing_task_number")
        ]

    def __str__(self):
        return f"{self.test.title} – Task {self.task_number}"


class WritingAttempt(models.Model):
    STATUS_CHOICES = [
        ("in_progress", "In progress"),
        ("submitted", "Submitted"),
        ("expired", "Expired"),
    ]
    MODE_CHOICES = [("exam", "Exam"), ("practice", "Practice")]
    GRACE_SECONDS = 60

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="writing_attempts")
    test = models.ForeignKey(WritingTest, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="in_progress")
    mode = models.CharField(max_length=8, choices=MODE_CHOICES, default="exam")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user} – {self.test} ({self.mode})"

    def deadline(self):
        return self.started_at + timedelta(minutes=self.test.duration_minutes)

    def seconds_left(self, now=None):
        now = now or timezone.now()
        return max(0, int((self.deadline() - now).total_seconds()))

    def is_expired(self, now=None):
        now = now or timezone.now()
        return now > self.deadline() + timedelta(seconds=self.GRACE_SECONDS)

    @property
    def remaining_seconds(self):
        return self.seconds_left()


class WritingResponse(models.Model):
    attempt = models.ForeignKey(WritingAttempt, on_delete=models.CASCADE, related_name="responses")
    task = models.ForeignKey(WritingTask, on_delete=models.CASCADE, related_name="responses")
    text = models.TextField(blank=True)
    word_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["attempt", "task"], name="unique_writing_response_per_task")
        ]
        ordering = ["task__task_number"]

    def __str__(self):
        return f"{self.attempt} – Task {self.task.task_number}"

    def save(self, *args, **kwargs):
        self.word_count = len((self.text or "").split())
        super().save(*args, **kwargs)


class WritingScore(models.Model):
    response = models.OneToOneField(WritingResponse, on_delete=models.CASCADE, related_name="score")
    criterion_1 = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    criterion_2 = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    criterion_3 = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    criterion_4 = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    feedback = models.TextField(blank=True)
    scored_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="writing_scores")
    scored_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Score for {self.response}"


class WritingEvaluation(models.Model):
    STATUS_CHOICES = [
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    response = models.ForeignKey(
        WritingResponse, on_delete=models.CASCADE, related_name="ai_evaluations"
    )
    request_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    result = models.JSONField(null=True, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at", "status"], name="writing_eval_created_status"),
        ]

    def __str__(self):
        return f"AI evaluation for {self.response} ({self.status})"
