"""Production settings.

Production must receive secrets and infrastructure settings from the
environment. Nothing sensitive is hardcoded here.
"""

import os

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


DEBUG = False

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY in {"change-me", "django-insecure-local-dev-only"}:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set for production.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set for production.")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL must be set for production.")

DATABASES = {
    "default": dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        ssl_require=env_bool("DATABASE_SSL_REQUIRE", True),  # noqa: F405
    )
}

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")  # noqa: F405

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(  # noqa: F405
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    True,
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", True)  # noqa: F405
