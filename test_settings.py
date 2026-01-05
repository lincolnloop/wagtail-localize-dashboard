"""
Django settings for running tests.
"""

import os

# Build paths inside the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "test-secret-key-for-testing-only"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["*"]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Wagtail apps
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "taggit",
    "modelcluster",
    # wagtail-localize
    "wagtail_localize",
    "wagtail_localize.locales",
    # Our library
    "wagtail_localize_dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = []

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Wagtail settings
WAGTAIL_SITE_NAME = "Test Site"
WAGTAILADMIN_BASE_URL = "http://localhost:8000"

# wagtail-localize settings
WAGTAIL_CONTENT_LANGUAGES = LANGUAGES = [
    ("en", "English"),
    ("fr", "French"),
    ("de", "German"),
    ("es", "Spanish"),
]

WAGTAIL_I18N_ENABLED = True

# wagtail-localize-dashboard settings (for testing)
WAGTAIL_LOCALIZE_DASHBOARD_ENABLED = True
WAGTAIL_LOCALIZE_DASHBOARD_AUTO_UPDATE = True
WAGTAIL_LOCALIZE_DASHBOARD_TRACK_PAGES = True
WAGTAIL_LOCALIZE_DASHBOARD_SHOW_IN_MENU = True
WAGTAIL_LOCALIZE_DASHBOARD_MENU_LABEL = "Translation Progress"
WAGTAIL_LOCALIZE_DASHBOARD_MENU_ICON = "doc-full-inverse"
WAGTAIL_LOCALIZE_DASHBOARD_MENU_ORDER = 300

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
