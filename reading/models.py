import re
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

QTYPE_CHOICES = [
    ("tfng", "True / False / Not Given"),
    ("ynng", "Yes / No / Not Given"),
    ("mcq", "Multiple choice"),
    ("matching", "Matching"),
    ("completion", "Sentence / note completion"),
    ("short", "Short answer"),
]
TFNG = [{"key": k, "text": k} for k in ("TRUE", "FALSE", "NOT GIVEN")]
YNNG = [{"key": k, "text": k} for k in ("YES", "NO", "NOT GIVEN")]
_LABEL = re.compile(r"^\[([A-Za-z]{1,2})\]\s*")
GRACE_SECONDS = 60


class ReadingTest(models.Model):
    MODULES = [("academic", "Academic"), ("general", "General Training")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    module = models.CharField(max_length=10, choices=MODULES, default="academic")
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    source_name = models.CharField(max_length=200, blank=True, help_text="Where this test comes from.")
    source_url = models.URLField(blank=True)
    license_note = models.CharField(max_length=300, blank=True, help_text="Why you are allowed to use it.")
    translations = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional word translations, grouped by language.",
    )
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def question_count(self):
        return Question.objects.filter(group__passage__test=self).count()


class Passage(models.Model):
    test = models.ForeignKey(ReadingTest, on_delete=models.CASCADE, related_name="passages")
    order = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    text = models.TextField(help_text="Separate paragraphs with a blank line. Start a paragraph with [A], [B]... to label it.")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.test.title} – {self.title}"

    def paragraphs(self):
        out = []
        for block in re.split(r"\n\s*\n", self.text.strip()):
            block = block.strip()
            if not block:
                continue
            m = _LABEL.match(block)
            if m:
                out.append({"label": m.group(1).upper(), "text": block[m.end():]})
            else:
                out.append({"label": "", "text": block})
        return out


class QuestionGroup(models.Model):
    passage = models.ForeignKey(Passage, on_delete=models.CASCADE, related_name="groups")
    order = models.PositiveIntegerField(default=1)
    qtype = models.CharField(max_length=12, choices=QTYPE_CHOICES)
    instruction = models.TextField(blank=True)
    options = models.JSONField(default=list, blank=True,
                               help_text='Matching only: [{"key": "A", "text": "..."}]')

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.passage.title}: {self.get_qtype_display()}"

    def number_range(self):
        nums = [q.number for q in self.questions.all()]
        if not nums:
            return ""
        return str(nums[0]) if len(nums) == 1 else f"{min(nums)}–{max(nums)}"


class Question(models.Model):
    group = models.ForeignKey(QuestionGroup, on_delete=models.CASCADE, related_name="questions")
    number = models.PositiveIntegerField()
    text = models.TextField(help_text="For gap-fill, mark the blank with ____")
    options = models.JSONField(default=list, blank=True,
                               help_text='Multiple choice only: [{"key": "A", "text": "..."}]')
    answer = models.CharField(max_length=255, help_text="Alternatives separated by |")
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ["number", "id"]

    def __str__(self):
        return f"Q{self.number}"

    @property
    def choices(self):
        t = self.group.qtype
        if t == "tfng":
            return TFNG
        if t == "ynng":
            return YNNG
        if t == "mcq":
            return self.options
        if t == "matching":
            return self.group.options
        return []

    @property
    def text_parts(self):
        before, sep, after = self.text.partition("____")
        return [before, after]

    def expected_display(self):
        return " / ".join(a.strip() for a in self.answer.split("|") if a.strip())


class Attempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_attempts")
    test = models.ForeignKey(ReadingTest, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    answers = models.JSONField(default=dict, blank=True)
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    band = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    seconds_spent = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user} – {self.test}"

    def deadline(self):
        return self.started_at + timedelta(minutes=self.test.duration_minutes)

    def seconds_left(self, now=None):
        now = now or timezone.now()
        return max(0, int((self.deadline() - now).total_seconds()))

    def is_expired(self, now=None):
        now = now or timezone.now()
        return now > self.deadline() + timedelta(seconds=GRACE_SECONDS)
