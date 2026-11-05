import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


DEBUG = env_bool("DEBUG", False)
TESTING = "test" in sys.argv

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "insecure-dev-key-not-for-production"
    else:
        raise RuntimeError("SECRET_KEY must be set when DEBUG is off.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "reading",
    "writing",
    "listening",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
CSRF_FAILURE_VIEW = "writing.views.csrf_failure"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database: test-only override; production continues to use DATABASE_URL ---
_test_db_url = os.environ.get("TEST_DATABASE_URL", "").strip()
_db_url = (
    _test_db_url
    if TESTING and _test_db_url
    else os.environ.get("DATABASE_URL", "").strip()
)
if _db_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            conn_health_checks=True,
            disable_server_side_cursors=True,  # needed behind Neon's pooled (pgbouncer) endpoint
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if TESTING:
    _test_database = DATABASES["default"]
    if (
        _test_database["ENGINE"] != "django.db.backends.postgresql"
        or _test_database.get("HOST", "").lower()
        not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise RuntimeError(
            "Tests require local PostgreSQL. Set TEST_DATABASE_URL to a local "
            "PostgreSQL server; remote databases and SQLite are not allowed."
        )
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    TEST_RUNNER = "core.test_runner.NoNetworkDiscoverRunner"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --- Security (active in production) ---
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not TESTING)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000 if not TESTING else 0
    SECURE_CONTENT_TYPE_NOSNIFF = True

# --- AI chat. Provider keys stay on the server and are never sent to the browser. ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_THINKING_LEVEL = os.environ.get("GEMINI_THINKING_LEVEL") or None
_gemini_thinking_budget = os.environ.get("GEMINI_THINKING_BUDGET")
GEMINI_THINKING_BUDGET = (
    int(_gemini_thinking_budget)
    if _gemini_thinking_budget is not None and _gemini_thinking_budget.strip()
    else None
)
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "25"))
GEMINI_503_RETRIES = int(os.environ.get("GEMINI_503_RETRIES", "2"))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
CHAT_AI_PROVIDER = os.environ.get("CHAT_AI_PROVIDER", "").strip().lower() or (
    "groq" if GROQ_API_KEY else "gemini"
)
GROQ_CHAT_MODEL = os.environ.get("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
GROQ_CHAT_MAX_TOKENS = int(os.environ.get("GROQ_CHAT_MAX_TOKENS", "2000"))
GROQ_CHAT_REASONING_EFFORT = os.environ.get("GROQ_CHAT_REASONING_EFFORT", "low") or None
CHAT_AI_FALLBACK_FROM_GROQ = env_bool("CHAT_AI_FALLBACK_FROM_GROQ", True)
CHAT_DAILY_LIMIT = int(os.environ.get("CHAT_DAILY_LIMIT", "40"))
CHAT_MAX_MESSAGE_CHARS = 2000

# --- AI Writing evaluation (Groq) ---
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
GROQ_MAX_TOKENS = int(os.environ.get("GROQ_MAX_TOKENS", "4000"))
GROQ_REASONING_EFFORT = os.environ.get("GROQ_REASONING_EFFORT") or None
GROQ_EVALUATIONS_DAILY_LIMIT = int(os.environ.get("GROQ_EVALUATIONS_DAILY_LIMIT", "3"))

# --- Email: Resend SMTP ---
EMAIL_HOST = "smtp.resend.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "resend"
EMAIL_HOST_PASSWORD = os.environ.get("RESEND_API_KEY", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "onboarding@resend.dev")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
