"""Deployment checks for production readiness."""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


PLACEHOLDER_SECRET_KEYS = {
    "",
    "change-me",
    "django-insecure-local-dev-only",
    "replace-me",
    "replace-with-generated-production-secret",
}


def _is_production_mode():
    return bool(getattr(settings, "PRODUCTION", False) or getattr(settings, "DJANGO_PRODUCTION", False))


def _cache_backend_name():
    return settings.CACHES.get("default", {}).get("BACKEND", "")


def _database_engine_name():
    return settings.DATABASES.get("default", {}).get("ENGINE", "")


@register(Tags.security)
def production_readiness_checks(app_configs, **kwargs):
    if not _is_production_mode():
        return []

    issues = []

    if settings.DEBUG:
        issues.append(
            Error(
                "DEBUG must be disabled in production.",
                hint="Set DJANGO_DEBUG=false for production deployments.",
                id="clinic.E001",
            )
        )

    secret_key = str(getattr(settings, "SECRET_KEY", "") or "")
    if secret_key in PLACEHOLDER_SECRET_KEYS or secret_key.startswith("django-insecure"):
        issues.append(
            Error(
                "SECRET_KEY is missing or uses a placeholder value.",
                hint="Set DJANGO_SECRET_KEY to a unique generated secret outside source control.",
                id="clinic.E002",
            )
        )

    allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    if not allowed_hosts or "*" in allowed_hosts:
        issues.append(
            Error(
                "ALLOWED_HOSTS must be locked to production hostnames.",
                hint="Set DJANGO_ALLOWED_HOSTS to the exact public hostnames.",
                id="clinic.E003",
            )
        )

    csrf_trusted_origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
    if allowed_hosts and not csrf_trusted_origins:
        issues.append(
            Error(
                "CSRF_TRUSTED_ORIGINS is empty in production mode.",
                hint="Set DJANGO_CSRF_TRUSTED_ORIGINS to HTTPS origins for each production domain.",
                id="clinic.E004",
            )
        )

    cache_backend = _cache_backend_name()
    if cache_backend.endswith(".LocMemCache"):
        issues.append(
            Error(
                "Production cache uses LocMemCache.",
                hint="Set CACHE_URL to a shared cache backend such as Redis for booking rate limits.",
                id="clinic.E005",
            )
        )

    database_engine = _database_engine_name()
    if database_engine.endswith(".sqlite3"):
        issues.append(
            Error(
                "Production database uses SQLite.",
                hint="Set DATABASE_URL to a PostgreSQL database for production.",
                id="clinic.E006",
            )
        )

    if getattr(settings, "BOOKING_TRUST_X_FORWARDED_FOR", False) and not getattr(
        settings,
        "BOOKING_TRUSTED_PROXY_CONFIGURED",
        False,
    ):
        issues.append(
            Warning(
                "BOOKING_TRUST_X_FORWARDED_FOR is enabled without proxy attestation.",
                hint=(
                    "Only enable it behind a trusted reverse proxy that strips client-supplied "
                    "X-Forwarded-For and sets its own header; then set BOOKING_TRUSTED_PROXY_CONFIGURED=true."
                ),
                id="clinic.W001",
            )
        )

    return issues
