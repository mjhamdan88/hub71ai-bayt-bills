import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "apps"))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-development-only")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [x.strip() for x in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "django.contrib.humanize", "channels", "django_ace", "reversion",
    "unicom", "unicrm", "unibot", "core",
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
    "reversion.middleware.RevisionMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
CHANNEL_LAYERS = {"default": {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {"hosts": [os.environ.get("REDIS_URL", "redis://127.0.0.1:6381/0")]},
}}

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("DB_NAME", "unistack"),
    "USER": os.environ.get("DB_USER", "unistack"),
    "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "unistack-local"),
    "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
    "PORT": os.environ.get("DB_PORT", "5433"),
}}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DJANGO_PUBLIC_ORIGIN = os.environ.get("DJANGO_PUBLIC_ORIGIN", "http://localhost:8000").rstrip("/")
OPENAI_API_KEY = os.environ.get("PORTACODE_RESPONSES_API_KEY", "portacode-local")
OPENAI_BASE_URL = os.environ.get("PORTACODE_RESPONSES_BASE_URL", "http://127.0.0.1:61789/v1")
PORTACODE_LLM_MODEL = os.environ.get("PORTACODE_LLM_MODEL", "gpt-5.6-terra")
CREDENTIAL_ENCRYPTION_KEY = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "")
UNICOM_TINYMCE_API_KEY = os.environ.get("UNICOM_TINYMCE_API_KEY", "")
UNICRM_AUTO_START_SCHEDULER = False
UNICRM_DISABLE_GP_POLLER = True
UNIBOT_DEFINITIONS_DIR = BASE_DIR / "data" / "definitions"

# Upstream helpers instantiate OpenAI directly; keep their client defaults local.
os.environ.setdefault("OPENAI_BASE_URL", OPENAI_BASE_URL)
