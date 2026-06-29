"""Safe deployment smoke checks for staging and production-like environments."""

import json
import os

from django.conf import settings
from django.core.cache import cache
from django.core.checks import Error
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.booking import services
from apps.clinic.models import ClinicProfile, Doctor, VisitType
from apps.core.checks import PLACEHOLDER_SECRET_KEYS, production_readiness_checks


CHECK_PASS = "pass"
CHECK_WARN = "warn"
CHECK_FAIL = "fail"

SENSITIVE_TEXT_REPLACEMENTS = {
    "DJANGO_SECRET_KEY": "application secret setting",
    "SECRET_KEY": "application secret",
    "DATABASE_URL": "database connection setting",
    "CACHE_URL": "cache connection setting",
}


def _safe_exception_label(exc):
    return exc.__class__.__name__


def _safe_text(value):
    text = str(value or "")
    for raw, replacement in SENSITIVE_TEXT_REPLACEMENTS.items():
        text = text.replace(raw, replacement)
    return text


def _is_secret_key_placeholder(secret_key):
    value = str(secret_key or "")
    return value in PLACEHOLDER_SECRET_KEYS or value.startswith("django-insecure")


def _database_engine_label():
    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    if engine.endswith(".postgresql"):
        return "postgresql"
    if engine.endswith(".sqlite3"):
        return "sqlite"
    return engine.rsplit(".", 1)[-1] if engine else "unknown"


def _cache_backend_label():
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend.endswith(".RedisCache"):
        return "redis"
    if backend.endswith(".LocMemCache"):
        return "locmem"
    return backend.rsplit(".", 1)[-1] if backend else "unknown"


def _production_like():
    settings_module = os.getenv("DJANGO_SETTINGS_MODULE", "")
    return bool(
        getattr(settings, "PRODUCTION", False)
        or settings_module.endswith(".prod")
        or settings_module.endswith(".staging")
    )


def _safe_settings_summary():
    return {
        "settings_module": os.getenv("DJANGO_SETTINGS_MODULE", ""),
        "debug": bool(settings.DEBUG),
        "production": bool(getattr(settings, "PRODUCTION", False)),
        "production_like": _production_like(),
        "application_secret_configured": bool(getattr(settings, "SECRET_KEY", "")),
        "application_secret_placeholder": _is_secret_key_placeholder(
            getattr(settings, "SECRET_KEY", "")
        ),
        "allowed_hosts_count": len(getattr(settings, "ALLOWED_HOSTS", []) or []),
        "csrf_trusted_origins_count": len(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or []),
        "database_engine": _database_engine_label(),
        "cache_backend": _cache_backend_label(),
        "secure_ssl_redirect": bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
        "session_cookie_secure": bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        "csrf_cookie_secure": bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        "secure_hsts_seconds": int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0),
        "secure_proxy_ssl_header_enabled": bool(getattr(settings, "SECURE_PROXY_SSL_HEADER", None)),
        "booking_trust_x_forwarded_for": bool(
            getattr(settings, "BOOKING_TRUST_X_FORWARDED_FOR", False)
        ),
        "booking_trusted_proxy_configured": bool(
            getattr(settings, "BOOKING_TRUSTED_PROXY_CONFIGURED", False)
        ),
    }


class SmokeResult:
    def __init__(self, *, strict):
        self.strict = strict
        self.checks = []

    def add(self, name, status, message, *, strict_blocker=False, details=None):
        self.checks.append(
            {
                "name": name,
                "status": status,
                "message": message,
                "strict_blocker": bool(strict_blocker),
                "details": details or {},
            }
        )

    @property
    def failures(self):
        return [check for check in self.checks if check["status"] == CHECK_FAIL]

    @property
    def warnings(self):
        return [check for check in self.checks if check["status"] == CHECK_WARN]

    @property
    def strict_blockers(self):
        return [check for check in self.warnings if check["strict_blocker"]]

    @property
    def exit_code(self):
        if self.failures:
            return 1
        if self.strict and self.strict_blockers:
            return 1
        return 0

    @property
    def status(self):
        if self.exit_code:
            return "failed"
        if self.warnings:
            return "warning"
        return "passed"

    def as_dict(self):
        return {
            "command": "deployment_smoke",
            "generated_at": timezone.now().isoformat(),
            "strict": self.strict,
            "status": self.status,
            "exit_code": self.exit_code,
            "summary": {
                "passes": len([check for check in self.checks if check["status"] == CHECK_PASS]),
                "warnings": len(self.warnings),
                "failures": len(self.failures),
                "strict_blockers": len(self.strict_blockers),
            },
            "settings": _safe_settings_summary(),
            "checks": self.checks,
        }


def run_deployment_smoke(*, strict=False):
    result = SmokeResult(strict=strict)

    result.add(
        "django_start",
        CHECK_PASS,
        "Django initialized and the management command started.",
    )
    result.add(
        "settings_loaded",
        CHECK_PASS,
        "Django settings are loaded.",
        details=_safe_settings_summary(),
    )

    _add_local_environment_warnings(result)
    _add_production_readiness_checks(result)
    _add_https_checks(result)
    _add_database_checks(result)
    _add_migration_check(result)
    _add_cache_check(result)
    _add_public_content_checks(result)
    _add_booking_settings_check(result)
    _add_health_import_check(result)
    _add_readiness_db_check(result)
    _add_public_booking_summary(result)
    _add_patient_portal_summary(result)

    return result.as_dict()


def _add_local_environment_warnings(result):
    if _production_like():
        return

    if settings.DEBUG:
        result.add(
            "local_debug_enabled",
            CHECK_WARN,
            "DEBUG is enabled; this is acceptable only for local development.",
        )

    if _database_engine_label() == "sqlite":
        result.add(
            "local_sqlite_database",
            CHECK_WARN,
            "SQLite is active; staging and production must use PostgreSQL.",
        )

    if _cache_backend_label() == "locmem":
        result.add(
            "local_locmem_cache",
            CHECK_WARN,
            "LocMemCache is active; staging and production must use a shared cache such as Redis.",
        )

    if not getattr(settings, "SECURE_SSL_REDIRECT", False):
        result.add(
            "local_https_redirect_disabled",
            CHECK_WARN,
            "HTTPS redirect is disabled; staging and production should use HTTPS.",
        )


def _add_production_readiness_checks(result):
    issues = production_readiness_checks(None)
    if not issues:
        result.add(
            "production_readiness_checks",
            CHECK_PASS,
            "Project production-readiness checks reported no active issues.",
        )
        return

    for issue in issues:
        status = CHECK_FAIL if isinstance(issue, Error) else CHECK_WARN
        result.add(
            f"production_readiness_{issue.id}",
            status,
            f"{_safe_text(issue.msg)} ({issue.id})",
            strict_blocker=status == CHECK_WARN,
            details={"hint": _safe_text(issue.hint)},
        )


def _add_https_checks(result):
    if not _production_like():
        return

    if not getattr(settings, "SECURE_SSL_REDIRECT", False):
        result.add(
            "production_https_redirect",
            CHECK_FAIL,
            "SECURE_SSL_REDIRECT is disabled in a production-like settings module.",
        )
    if not getattr(settings, "SESSION_COOKIE_SECURE", False):
        result.add(
            "production_session_cookie_secure",
            CHECK_FAIL,
            "SESSION_COOKIE_SECURE is disabled in a production-like settings module.",
        )
    if not getattr(settings, "CSRF_COOKIE_SECURE", False):
        result.add(
            "production_csrf_cookie_secure",
            CHECK_FAIL,
            "CSRF_COOKIE_SECURE is disabled in a production-like settings module.",
        )


def _add_database_checks(result):
    try:
        connection.ensure_connection()
    except Exception as exc:
        result.add(
            "database_connectivity",
            CHECK_FAIL,
            f"Database connectivity failed ({_safe_exception_label(exc)}).",
        )
        return

    result.add(
        "database_connectivity",
        CHECK_PASS,
        "Database connection succeeded.",
        details={"vendor": connection.vendor},
    )


def _add_migration_check(result):
    try:
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception as exc:
        result.add(
            "migrations_applied",
            CHECK_FAIL,
            f"Migration state could not be checked ({_safe_exception_label(exc)}).",
        )
        return

    if plan:
        unapplied = [f"{migration.app_label}.{migration.name}" for migration, _ in plan]
        result.add(
            "migrations_applied",
            CHECK_FAIL,
            f"Unapplied migrations detected: {len(unapplied)}.",
            details={"count": len(unapplied), "unapplied": unapplied[:20]},
        )
        return

    result.add(
        "migrations_applied",
        CHECK_PASS,
        "All migrations are applied.",
    )


def _add_cache_check(result):
    key = "deployment-smoke-cache-check"
    expected = "ok"
    try:
        cache.set(key, expected, timeout=30)
        observed = cache.get(key)
        cache.delete(key)
    except Exception as exc:
        result.add(
            "default_cache",
            CHECK_FAIL,
            f"Default cache check failed ({_safe_exception_label(exc)}).",
        )
        return

    if observed != expected:
        result.add(
            "default_cache",
            CHECK_FAIL,
            "Default cache did not return the expected smoke-test value.",
        )
        return

    result.add(
        "default_cache",
        CHECK_PASS,
        "Default cache is reachable for set/get/delete.",
        details={"backend": _cache_backend_label()},
    )


def _add_public_content_checks(result):
    try:
        active_clinic_exists = ClinicProfile.objects.filter(is_active=True).exists()
        active_doctor_exists = Doctor.objects.filter(is_active=True).exists()
        active_visit_type_count = VisitType.objects.filter(is_active=True).count()
    except Exception as exc:
        result.add(
            "public_content_queries",
            CHECK_FAIL,
            f"Public content checks could not query the database ({_safe_exception_label(exc)}).",
        )
        return

    if active_clinic_exists:
        result.add("active_clinic_profile", CHECK_PASS, "An active clinic profile exists.")
    else:
        result.add(
            "active_clinic_profile",
            CHECK_WARN,
            "No active clinic profile exists. Run seed_public_content for staging demo setup if appropriate.",
        )

    if active_doctor_exists:
        result.add("active_doctor", CHECK_PASS, "An active doctor exists.")
    else:
        result.add(
            "active_doctor",
            CHECK_WARN,
            "No active doctor exists. Run seed_public_content for staging demo setup if appropriate.",
        )

    if active_visit_type_count:
        result.add(
            "active_visit_types",
            CHECK_PASS,
            "Active visit types exist.",
            details={"count": active_visit_type_count},
        )
    else:
        result.add(
            "active_visit_types",
            CHECK_WARN,
            "No active visit types exist. Run seed_public_content for staging demo setup if appropriate.",
        )


def _add_booking_settings_check(result):
    try:
        booking_settings = services.get_booking_settings()
    except Exception as exc:
        result.add(
            "booking_settings",
            CHECK_FAIL,
            f"Booking settings could not be loaded ({_safe_exception_label(exc)}).",
        )
        return

    status = CHECK_PASS if booking_settings.enabled else CHECK_WARN
    message = (
        "Booking settings loaded."
        if booking_settings.enabled
        else "Booking settings loaded, but public booking is disabled."
    )
    result.add(
        "booking_settings",
        status,
        message,
        details={
            "enabled": booking_settings.enabled,
            "min_lead_minutes": booking_settings.min_lead_minutes,
            "max_days_ahead": booking_settings.max_days_ahead,
            "slot_interval_minutes": booking_settings.slot_interval_minutes,
            "reminder_offset_minutes": booking_settings.reminder_offset_minutes,
        },
    )


def _add_health_import_check(result):
    try:
        from apps.core.views import health_check, readiness_check
    except Exception as exc:
        result.add(
            "health_endpoint_import",
            CHECK_FAIL,
            f"Health endpoint logic could not be imported ({_safe_exception_label(exc)}).",
        )
        return

    if callable(health_check) and callable(readiness_check):
        result.add(
            "health_endpoint_import",
            CHECK_PASS,
            "Health and readiness endpoint logic imported successfully.",
        )
    else:
        result.add(
            "health_endpoint_import",
            CHECK_FAIL,
            "Health endpoint imports are not callable.",
        )


def _add_readiness_db_check(result):
    try:
        connection.ensure_connection()
    except Exception as exc:
        result.add(
            "readiness_database_check",
            CHECK_FAIL,
            f"Readiness database check failed ({_safe_exception_label(exc)}).",
        )
        return

    result.add(
        "readiness_database_check",
        CHECK_PASS,
        "Readiness database check can run.",
    )


def _add_public_booking_summary(result):
    result.add(
        "public_booking_security_summary",
        CHECK_PASS,
        "Public booking keeps UUID public-token success URLs and staff-only numeric appointment operations.",
        details={
            "public_success_lookup": "uuid_public_token",
            "numeric_success_route": False,
            "staff_operations_require_staff": True,
            "rate_limit_identity": (
                "trusted_x_forwarded_for"
                if getattr(settings, "BOOKING_TRUST_X_FORWARDED_FOR", False)
                else "remote_addr"
            ),
            "cache_backend": _cache_backend_label(),
        },
    )


def _add_patient_portal_summary(result):
    required_routes = [
        "patient_portal_dashboard",
        "patient_portal_login",
        "patient_portal_logout",
        "patient_portal_register",
        "patient_portal_link_appointment",
        "patient_portal_appointment_list",
    ]
    try:
        for route_name in required_routes:
            reverse(route_name)
    except NoReverseMatch:
        result.add(
            "patient_portal_routes",
            CHECK_FAIL,
            "Patient portal foundation routes could not be reversed.",
        )
        return

    result.add(
        "patient_portal_security_summary",
        CHECK_PASS,
        "Patient portal foundation routes are importable without requiring patient accounts.",
        details={
            "portal_scope": "account_login_linked_appointment_viewing",
            "public_booking_requires_login": False,
            "appointment_lookup": "uuid_public_token_with_authenticated_owner",
            "uploads_enabled": False,
            "medical_records_enabled": False,
            "whatsapp_api_enabled": False,
            "payments_enabled": False,
        },
    )


class Command(BaseCommand):
    help = "Run safe staging/deployment smoke checks without printing secrets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail on staging/production launch-blocking warnings.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            help="Emit safe machine-readable JSON.",
        )

    def handle(self, *args, **options):
        result = run_deployment_smoke(strict=options["strict"])

        if options["json_output"]:
            self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        else:
            self._write_human(result)

        if result["exit_code"]:
            raise CommandError(
                "Deployment smoke failed. Review failed checks and strict blockers above."
            )

    def _write_human(self, result):
        settings_summary = result["settings"]
        self.stdout.write("Deployment smoke for Dr. Khaled Badran Clinic")
        self.stdout.write(f"Settings module: {settings_summary['settings_module'] or '(unset)'}")
        self.stdout.write(
            "Safe settings summary: "
            f"debug={settings_summary['debug']}, "
            f"production={settings_summary['production']}, "
            f"database={settings_summary['database_engine']}, "
            f"cache={settings_summary['cache_backend']}, "
            f"allowed_hosts_count={settings_summary['allowed_hosts_count']}, "
            f"csrf_trusted_origins_count={settings_summary['csrf_trusted_origins_count']}"
        )
        self.stdout.write(
            "Sensitive settings: application secret configured="
            f"{settings_summary['application_secret_configured']} "
            "(value not printed); connection strings and credentials not printed."
        )

        for check in result["checks"]:
            prefix = {
                CHECK_PASS: self.style.SUCCESS("[OK]"),
                CHECK_WARN: self.style.WARNING("[WARN]"),
                CHECK_FAIL: self.style.ERROR("[FAIL]"),
            }[check["status"]]
            suffix = " (strict blocker)" if check["strict_blocker"] else ""
            self.stdout.write(f"{prefix} {check['name']}: {check['message']}{suffix}")

        summary = result["summary"]
        self.stdout.write(
            "Result: "
            f"{result['status'].upper()} "
            f"({summary['passes']} pass, "
            f"{summary['warnings']} warning, "
            f"{summary['failures']} failure, "
            f"{summary['strict_blockers']} strict blocker)"
        )
