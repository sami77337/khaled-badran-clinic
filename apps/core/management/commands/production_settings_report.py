"""Safe production-like settings report for staging validation."""

import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.checks import PLACEHOLDER_SECRET_KEYS


def _production_like():
    settings_module = os.getenv("DJANGO_SETTINGS_MODULE", "")
    return bool(
        getattr(settings, "PRODUCTION", False)
        or settings_module.endswith(".prod")
        or settings_module.endswith(".staging")
    )


def _database_backend_category():
    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if engine.endswith(".postgresql"):
        return "postgresql"
    if engine.endswith(".sqlite3"):
        return "sqlite"
    if not engine:
        return "unknown"
    return "other"


def _cache_backend_category():
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend.endswith(".RedisCache"):
        return "redis"
    if backend.endswith(".LocMemCache"):
        return "locmem"
    if not backend:
        return "unknown"
    return "other"


def _application_secret_placeholder():
    secret_key = str(getattr(settings, "SECRET_KEY", "") or "")
    return secret_key in PLACEHOLDER_SECRET_KEYS or secret_key.startswith("django-insecure")


def build_production_settings_report():
    return {
        "command": "production_settings_report",
        "generated_at": timezone.now().isoformat(),
        "settings_module": os.getenv("DJANGO_SETTINGS_MODULE", ""),
        "production_like": _production_like(),
        "debug": bool(getattr(settings, "DEBUG", False)),
        "application_secret_configured": bool(getattr(settings, "SECRET_KEY", "")),
        "application_secret_placeholder": _application_secret_placeholder(),
        "database_backend": _database_backend_category(),
        "cache_backend": _cache_backend_category(),
        "allowed_hosts_count": len(getattr(settings, "ALLOWED_HOSTS", []) or []),
        "csrf_trusted_origins_count": len(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []),
        "secure_ssl_redirect": bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
        "session_cookie_secure": bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        "csrf_cookie_secure": bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        "secure_hsts_enabled": int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0) > 0,
        "secure_hsts_include_subdomains": bool(
            getattr(settings, "SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
        ),
        "secure_hsts_preload": bool(getattr(settings, "SECURE_HSTS_PRELOAD", False)),
        "secure_proxy_ssl_header_enabled": bool(
            getattr(settings, "SECURE_PROXY_SSL_HEADER", None)
        ),
        "booking_trust_x_forwarded_for": bool(
            getattr(settings, "BOOKING_TRUST_X_FORWARDED_FOR", False)
        ),
        "booking_trusted_proxy_configured": bool(
            getattr(settings, "BOOKING_TRUSTED_PROXY_CONFIGURED", False)
        ),
        "safe_output_policy": "booleans_counts_and_backend_categories_only",
    }


class Command(BaseCommand):
    help = "Print a safe production-like settings report without secrets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emit safe machine-readable JSON.",
        )

    def handle(self, *args, **options):
        report = build_production_settings_report()
        if options["json_output"]:
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self.stdout.write("Production settings report for Dr. Khaled Badran Clinic")
        self.stdout.write("Safe output: booleans, counts, and backend categories only.")
        self.stdout.write(
            "Settings: "
            f"module={report['settings_module'] or '(unset)'}, "
            f"production_like={report['production_like']}, "
            f"debug={report['debug']}"
        )
        self.stdout.write(
            "Backends: "
            f"database={report['database_backend']}, "
            f"cache={report['cache_backend']}"
        )
        self.stdout.write(
            "Hosts and CSRF: "
            f"allowed_hosts_count={report['allowed_hosts_count']}, "
            f"csrf_trusted_origins_count={report['csrf_trusted_origins_count']}"
        )
        self.stdout.write(
            "HTTPS and cookies: "
            f"secure_ssl_redirect={report['secure_ssl_redirect']}, "
            f"session_cookie_secure={report['session_cookie_secure']}, "
            f"csrf_cookie_secure={report['csrf_cookie_secure']}, "
            f"hsts_enabled={report['secure_hsts_enabled']}"
        )
        self.stdout.write(
            "Proxy and booking IP trust: "
            f"secure_proxy_ssl_header_enabled={report['secure_proxy_ssl_header_enabled']}, "
            f"booking_trust_x_forwarded_for={report['booking_trust_x_forwarded_for']}, "
            f"booking_trusted_proxy_configured={report['booking_trusted_proxy_configured']}"
        )
        self.stdout.write(
            "Sensitive values are not printed: no application secret, connection "
            "strings, passwords, tokens, host values, or raw environment dumps."
        )
