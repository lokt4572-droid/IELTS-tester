# IELTS Practice (Django)

Reading tests with timed exam view, autosave, highlighter, instant marking and band estimate;
an AI tutor that can explain any question using the passage; PostgreSQL (Neon) storage.
Listening, Writing and Speaking have a place in `core/modules.py`.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in DATABASE_URL (Neon) and an AI provider key
python manage.py migrate
python manage.py createsuperuser
python manage.py makemigrations --check   # should say "No changes detected"
python manage.py test       # run the tests first
python manage.py import_reading sample_data/demo_system_check.json --publish
python manage.py runserver
```
Without `DATABASE_URL` the site falls back to a local SQLite file, so you can try it before connecting Neon.

## Running tests on local PostgreSQL

Set `TEST_DATABASE_URL` in `.env` to a local PostgreSQL database URL. It is used
only by `manage.py test`; normal runs continue to use `DATABASE_URL`. The test
role needs PostgreSQL's `CREATEDB` permission because Django creates and uses
its own `test_<database-name>` database. Do not use a production database URL.
The test runner blocks outbound network access (including unmocked HTTP calls),
and tests use Django's fast MD5 password hasher.

On Windows, in a PostgreSQL SQL shell connected as an administrator, create a
dedicated role:

```sql
CREATE ROLE ielts_test_user WITH LOGIN PASSWORD 'choose-a-local-test-password' CREATEDB;
```

Then add this to `.env`, URL-encoding any special characters in the password:

```dotenv
TEST_DATABASE_URL=postgresql://ielts_test_user:choose-a-local-test-password@127.0.0.1:5432/ielts_local
```

The command `python manage.py test writing --keepdb` will create/reuse
`test_ielts_local`; it will not use `ielts_local` itself as the test database.

## Adding real tests
Admin → Reading tests → **Import JSON** (or `python manage.py import_reading file.json --publish`).
Every test must name its `source_name` and a `license_note`. Format: see `sample_data/demo_system_check.json`.
Question types: `tfng`, `ynng`, `mcq`, `matching`, `completion`, `short`.
Gap-fill blanks are written `____`. Several accepted answers: `"windmills|wind mills"`.
Label passage paragraphs with `[A]`, `[B]` at the start of a paragraph.
Delete the demo test before launch.

## Writing import format
Use `python manage.py import_writing sample_data/demo_writing_1.json --publish`.
Every writing test must include `title`, `slug`, `module`, and `tasks` with exactly Task 1 and Task 2.
Unknown fields are ignored with a warning; missing optional values are fine.
```json
{
  "title": "Academic Writing Test 1",
  "slug": "academic-writing-1",
  "module": "academic",
  "duration_minutes": 60,
  "description": "...",
  "source_name": "...",
  "source_url": "https://example.com",
  "license_note": "...",
  "tasks": [
    {
      "task_number": 1,
      "instructions": "You should spend about 20 minutes on this task.",
      "prompt_text": "The chart below shows...",
      "image_file": "chart1.png",
      "image_alt": "Bar chart showing...",
      "min_words": 150,
      "suggested_minutes": 20,
      "sample_answer": "optional text",
      "sample_answer_band": 8.0
    },
    {
      "task_number": 2,
      "instructions": "You should spend about 40 minutes on this task.",
      "prompt_text": "Some people think...",
      "min_words": 250,
      "suggested_minutes": 40
    }
  ]
}
```
`image_file` is looked up in the same folder as the JSON file; if missing, the task is imported without an image and a warning is printed.

## Listening import format
Import one listening test with:

```bash
python manage.py import_listening sample_data/demo_listening_1.json --publish
```

Each test contains exactly four sections in order, and question numbers must
run continuously from 1 to 40. Every section needs an `audio_file` path and
`audio_seconds`. The top-level fields are `title`, `slug`, `description`,
`duration_minutes` (default 30), `review_seconds` (default 120), `source_name`,
`source_url`, `license_note`, and `sections`; `source_name` and `license_note`
are required. A section has `number`, `title`, `context`, `audio_file`,
`audio_seconds`, optional `preview_seconds` and `check_seconds` (both default
30), optional `transcript` and `image_file`, and its `groups`. The audio file
must exist in the same folder as the JSON.
Optional section and group `image_file` paths are resolved from that folder;
missing images are skipped with a warning, while missing audio is an error.
The importer copies assets to `MEDIA_ROOT/listening/`.

Each section contains ordered `groups`. Supported group types are `mcq`,
`mcq_multi`, `matching`, `completion`, `short`, and `diagram_label`.
Single-question groups use a `questions` array with `number`, `text`,
`answer`, optional question-level `options`, and optional `explanation`.
Option objects have a `key` and `text`. Matching and diagram-label options
are on the group. A multi-select group uses `choose`, `numbers`, `text`,
group `options`, and `answers` (one correct letter per question number).
Completion prompts mark each blank with `____`; accepted alternatives can be
separated with `|`, for example `"colour|color"`. Unknown fields are ignored
with warnings.

`sample_data/demo_listening_1.json` demonstrates the import structure and
question types. It is a format example, not an audio-ready test: add properly
licensed files named in its `audio_file` fields (and its optional plan image)
beside the JSON before importing it. For example, the sample's audio references
are `demo_listening_1_section_1.mp3` through
`demo_listening_1_section_4.mp3`.

The sound-check page uses `static/listening/sound-check.wav`, a local
one-second, 880 Hz mono PCM tone generated with Python's standard-library
`wave`, `math`, and `struct` modules. Run
`python scripts/generate_listening_sound_check.py` to regenerate it; no external
audio service or package is used.

### Optional passage translations
Add a top-level `translations` object to a test JSON. Each language needs a
`words` object; keys are lowercase base words or phrases. Optional `forms`
maps inflected forms to those keys:
```json
"translations": {
  "ru": {
    "words": {"carry out": {"t": "выполнять", "pos": "phrase"}},
    "forms": {"carried out": "carry out"}
  },
  "tg": {
    "words": {"carry out": {"t": "иҷро кардан"}}
  }
}
```
Translation data is optional. Invalid translation data is skipped with a
warning while the rest of the test is imported.

## Production environment variables
`SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`,
`GEMINI_API_KEY`, `GEMINI_MODEL`, `GROQ_API_KEY`, `CHAT_AI_PROVIDER`,
`GROQ_CHAT_MODEL`, `GROQ_CHAT_MAX_TOKENS`, `GROQ_CHAT_REASONING_EFFORT`,
`GEMINI_THINKING_LEVEL`, `GEMINI_THINKING_BUDGET`, `GEMINI_TIMEOUT_SECONDS`,
`GEMINI_503_RETRIES`, and `CHAT_AI_FALLBACK_FROM_GROQ`. Chat defaults to Groq
when `GROQ_API_KEY` is configured and otherwise defaults to Gemini; set
`CHAT_AI_PROVIDER` to explicitly choose the server-side default. Students do
not select a provider. Groq failures caused by timeouts, network errors, HTTP
429, or HTTP 5xx after retries can fall back once to Gemini; this is enabled by
default and can be disabled with `CHAT_AI_FALLBACK_FROM_GROQ=false`. HTTP 400,
401, 403, and 404 do not trigger fallback. Gemini chat timeout defaults to 25
seconds and it retries
HTTP 503 responses twice (with 1- and 2-second waits); timeouts and HTTP 429
are not retried. Its optional thinking level takes precedence over the optional
integer thinking budget (including `0`); neither is sent when both are unset.
Chat defaults are `openai/gpt-oss-20b`, 2000 output tokens, low reasoning
effort (sent only to supported models). The provider used is retained with
assistant messages for staff/admin inspection; students see no provider details.
`CHAT_DAILY_LIMIT` is shared by both providers, and unsuccessful provider
calls do not consume a slot.

Writing AI evaluation additionally uses `GROQ_MODEL`,
`GROQ_FALLBACK_MODEL`, `GROQ_MAX_TOKENS` (default 4000),
`GROQ_REASONING_EFFORT` (optional: `low`, `medium`, or `high`), and
`GROQ_EVALUATIONS_DAILY_LIMIT`. The model defaults are
`llama-3.3-70b-versatile` and `llama-3.1-8b-instant`; the daily limit defaults
to 3 successful fresh evaluations per user. Reasoning effort is sent only to
Groq models documented as supporting it. Staff can run
`python manage.py evaluate_writing <attempt_id> [--task 1|2] [--language en|ru|tg]`.
Add `--debug` to print Groq response diagnostics and the first 3000 characters
of model output when evaluation validation fails.
Build: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
Start: `gunicorn config.wsgi`
