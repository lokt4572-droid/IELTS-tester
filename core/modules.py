"""Registry of test modules shown on the home page and the tests hub.

To add a new module (Listening, Writing, ...): create a Django app, add its URLs,
then set `url_name` for its entry here. Entries with url_name=None show as "Planned".
"""

MODULES = [
    {
        "slug": "reading",
        "name": "Reading",
        "blurb": "Timed passages with every IELTS question type, instant scoring and a band estimate.",
        "url_name": "reading:list",
    },
    {
        "slug": "listening",
        "name": "Listening",
        "blurb": "Audio sections with the same timing and scoring flow.",
        "url_name": "listening:list",
    },
    {
        "slug": "writing",
        "name": "Writing",
        "blurb": "Task 1 and Task 2 with timed responses, live word counts, and estimated band scoring.",
        "url_name": "writing:list",
    },
    {
        "slug": "speaking",
        "name": "Speaking",
        "blurb": "Part 1–3 question banks and a practice partner.",
        "url_name": None,
    },
]
