import html as html_lib
import json
import os
import re
import subprocess
import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import ignore_warnings
from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import ClinicProfile, Doctor, VisitType
from apps.core import views as core_views
from apps.core.checks import production_readiness_checks
from apps.patients.models import Patient
from apps.records.models import (
    ClinicalNote,
    PublicCase,
    RecordMedia,
    RecordMediaFolder,
    VisitRecord,
)
from apps.records.public_cases import decode_public_case_title, encode_public_case_title
from config.settings.helpers import (
    build_cache_config,
    build_database_config,
    parse_bool,
    parse_int,
    parse_list,
)


class HealthRouteTests(TestCase):
    def test_health_route_responds(self):
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dr. Khaled Badran Clinic")
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_route_responds_without_internal_details(self):
        response = self.client.get(reverse("health_ready"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        content = response.content.decode()
        self.assertNotIn("sqlite", content.lower())
        self.assertNotIn("password", content.lower())

    def test_readiness_route_hides_database_failure_details(self):
        with patch("apps.core.views.connection.ensure_connection", side_effect=Exception("password=secret")):
            with self.assertLogs("django.request", level="ERROR"):
                response = self.client.get(reverse("health_ready"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotContains(response, "password", status_code=503)
        self.assertNotContains(response, "secret", status_code=503)

    def test_health_and_readiness_routes_do_not_expose_internal_details(self):
        responses = [
            self.client.get(reverse("health")),
            self.client.get(reverse("health_ready")),
        ]
        blocked_fragments = [
            "sqlite",
            "postgres",
            "redis",
            "database",
            "cache",
            "settings",
            "secret",
            "password",
            "traceback",
            "version",
            "hostname",
        ]

        for response in responses:
            self.assertIn(response.status_code, {200, 503})
            content = response.content.decode().lower()
            for fragment in blocked_fragments:
                with self.subTest(status=response.status_code, fragment=fragment):
                    self.assertNotIn(fragment, content)


class SettingsHelperTests(SimpleTestCase):
    def test_parse_bool_handles_common_values_and_defaults(self):
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("1"))
        self.assertFalse(parse_bool("false", default=True))
        self.assertFalse(parse_bool("0", default=True))
        self.assertTrue(parse_bool("not-a-bool", default=True))

    def test_parse_list_trims_empty_values(self):
        self.assertEqual(parse_list("clinic.example.com, www.example.com, "), ["clinic.example.com", "www.example.com"])
        self.assertEqual(parse_list("", default=["localhost"]), ["localhost"])

    def test_parse_int_enforces_bounds_and_defaults(self):
        self.assertEqual(parse_int("30", default=5, minimum=1), 30)
        self.assertEqual(parse_int("0", default=5, minimum=1), 5)
        self.assertEqual(parse_int("500", default=5, maximum=60), 60)
        self.assertEqual(parse_int("invalid", default=5), 5)

    def test_database_helper_uses_sqlite_fallback_for_local_development(self):
        databases = build_database_config("", sqlite_path=settings.BASE_DIR / "db.sqlite3")

        self.assertEqual(databases["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(databases["default"]["NAME"], settings.BASE_DIR / "db.sqlite3")

    def test_database_helper_parses_postgres_database_url(self):
        databases = build_database_config(
            "postgres://clinic_user:clinic_pass@db.example.test:5432/clinic_db",
            sqlite_path=settings.BASE_DIR / "db.sqlite3",
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )

        default = databases["default"]
        self.assertEqual(default["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(default["NAME"], "clinic_db")
        self.assertEqual(default["CONN_MAX_AGE"], 600)
        self.assertTrue(default["CONN_HEALTH_CHECKS"])

    def test_cache_helper_uses_locmem_without_cache_url(self):
        caches = build_cache_config("", key_prefix="test")

        self.assertEqual(caches["default"]["BACKEND"], "django.core.cache.backends.locmem.LocMemCache")
        self.assertEqual(caches["default"]["KEY_PREFIX"], "test")

    def test_cache_helper_supports_redis_cache_url(self):
        caches = build_cache_config("redis://redis.example.test:6379/1", key_prefix="test")

        self.assertEqual(caches["default"]["BACKEND"], "django.core.cache.backends.redis.RedisCache")
        self.assertEqual(caches["default"]["LOCATION"], "redis://redis.example.test:6379/1")


class LocalSettingsDefaultTests(SimpleTestCase):
    def test_local_settings_remain_development_oriented(self):
        self.assertFalse(settings.PRODUCTION)
        self.assertFalse(settings.BOOKING_TRUST_X_FORWARDED_FOR)
        if not os.environ.get("CACHE_URL"):
            self.assertEqual(
                settings.CACHES["default"]["BACKEND"],
                "django.core.cache.backends.locmem.LocMemCache",
            )


class ProductionReadinessCheckTests(SimpleTestCase):
    @override_settings(PRODUCTION=False, DEBUG=True, SECRET_KEY="change-me", ALLOWED_HOSTS=[])
    def test_local_mode_does_not_emit_production_readiness_errors(self):
        self.assertEqual(production_readiness_checks(None), [])

    @ignore_warnings(message="Overriding setting DATABASES can lead to unexpected behavior.")
    @override_settings(
        PRODUCTION=True,
        DEBUG=True,
        SECRET_KEY="change-me",
        ALLOWED_HOSTS=[],
        CSRF_TRUSTED_ORIGINS=[],
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"}},
        BOOKING_TRUST_X_FORWARDED_FOR=False,
    )
    def test_production_mode_flags_insecure_core_settings(self):
        issue_ids = {issue.id for issue in production_readiness_checks(None)}

        self.assertIn("clinic.E001", issue_ids)
        self.assertIn("clinic.E002", issue_ids)
        self.assertIn("clinic.E003", issue_ids)
        self.assertIn("clinic.E005", issue_ids)
        self.assertIn("clinic.E006", issue_ids)

    @ignore_warnings(message="Overriding setting DATABASES can lead to unexpected behavior.")
    @override_settings(
        PRODUCTION=True,
        DEBUG=False,
        SECRET_KEY="test-only-long-production-secret-placeholder",
        ALLOWED_HOSTS=["clinic.example.test"],
        CSRF_TRUSTED_ORIGINS=[],
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "redis://redis.example.test:6379/1",
            }
        },
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "clinic_db"}},
        BOOKING_TRUST_X_FORWARDED_FOR=False,
    )
    def test_production_mode_requires_csrf_trusted_origins_with_hosts(self):
        issue_ids = {issue.id for issue in production_readiness_checks(None)}

        self.assertIn("clinic.E004", issue_ids)

    @ignore_warnings(message="Overriding setting DATABASES can lead to unexpected behavior.")
    @override_settings(
        PRODUCTION=True,
        DEBUG=False,
        SECRET_KEY="test-only-long-production-secret-placeholder",
        ALLOWED_HOSTS=["clinic.example.test"],
        CSRF_TRUSTED_ORIGINS=["https://clinic.example.test"],
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "redis://redis.example.test:6379/1",
            }
        },
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "clinic_db"}},
        BOOKING_TRUST_X_FORWARDED_FOR=False,
    )
    def test_production_mode_passes_core_readiness_checks_when_configured(self):
        self.assertEqual(production_readiness_checks(None), [])

    @ignore_warnings(message="Overriding setting DATABASES can lead to unexpected behavior.")
    @override_settings(
        PRODUCTION=True,
        DEBUG=False,
        SECRET_KEY="test-only-long-production-secret-placeholder",
        ALLOWED_HOSTS=["clinic.example.test"],
        CSRF_TRUSTED_ORIGINS=["https://clinic.example.test"],
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "redis://redis.example.test:6379/1",
            }
        },
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "clinic_db"}},
        BOOKING_TRUST_X_FORWARDED_FOR=True,
        BOOKING_TRUSTED_PROXY_CONFIGURED=False,
    )
    def test_forwarded_for_trust_requires_proxy_attestation(self):
        issue_ids = {issue.id for issue in production_readiness_checks(None)}

        self.assertIn("clinic.W001", issue_ids)


class DeploymentSmokeCommandTests(TestCase):
    def call_smoke(self, **options):
        output = StringIO()
        call_command("deployment_smoke", stdout=output, **options)
        return output.getvalue()

    def create_patient_appointment(self):
        user = get_user_model().objects.create_user(
            username="+962799999999",
            email="private-patient@example.test",
            password="test-password",
            first_name="Private Patient",
        )
        doctor = Doctor.objects.create(
            full_name_ar="ط®ط§ظ„ط¯ ط­ط³ط§ظ† ط¨ط¯ط±ط§ظ†",
            full_name_en="Khaled Hassan Badran",
            title_en="Dr.",
            is_active=True,
        )
        visit_type = VisitType.objects.create(
            doctor=doctor,
            name_ar="ظƒط´ظپ",
            name_en="Private Visit",
            duration_minutes=30,
            is_active=True,
        )
        patient = Patient.objects.create(
            user=user,
            full_name="Batch Ten Private Patient",
            phone_raw="0799999999",
            phone_e164="+962799999999",
        )
        starts_at = timezone.now() + timedelta(days=1)
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
        )

    def test_default_mode_succeeds_in_local_development_with_warnings(self):
        output = self.call_smoke()

        self.assertIn("Deployment smoke for Dr. Khaled Badran Clinic", output)
        self.assertIn("[WARN]", output)
        self.assertIn("Result: WARNING", output)

    def test_json_mode_outputs_valid_safe_json(self):
        output = self.call_smoke(json_output=True)
        payload = json.loads(output)

        self.assertEqual(payload["command"], "deployment_smoke")
        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["exit_code"], 0)
        self.assertIn("checks", payload)
        self.assertGreaterEqual(payload["summary"]["warnings"], 1)
        self.assertEqual(
            set(payload.keys()),
            {
                "checks",
                "command",
                "exit_code",
                "generated_at",
                "settings",
                "status",
                "strict",
                "summary",
            },
        )

    def test_patient_portal_account_security_routes_are_summarized(self):
        output = self.call_smoke(json_output=True)
        payload = json.loads(output)
        portal_check = next(
            check for check in payload["checks"] if check["name"] == "patient_portal_security_summary"
        )

        self.assertTrue(portal_check["details"]["account_security_routes"])
        self.assertFalse(portal_check["details"]["email_password_reset_enabled"])
        self.assertTrue(portal_check["details"]["approved_medical_records_enabled"])
        self.assertFalse(portal_check["details"]["public_medical_file_urls"])

    def test_public_booking_security_summary_is_summarized(self):
        output = self.call_smoke(json_output=True)
        payload = json.loads(output)
        booking_check = next(
            check for check in payload["checks"] if check["name"] == "public_booking_security_summary"
        )

        self.assertEqual(booking_check["details"]["public_success_lookup"], "uuid_public_token")
        self.assertFalse(booking_check["details"]["numeric_success_route"])
        self.assertTrue(booking_check["details"]["staff_operations_require_staff"])

    def test_project_consolidation_and_prohibited_feature_flags_are_summarized(self):
        output = self.call_smoke(json_output=True)
        payload = json.loads(output)
        consolidation_check = next(
            check for check in payload["checks"] if check["name"] == "project_consolidation_summary"
        )
        prohibited_check = next(
            check for check in payload["checks"] if check["name"] == "prohibited_feature_flags"
        )

        self.assertEqual(consolidation_check["status"], "pass")
        self.assertEqual(consolidation_check["details"]["public_success_lookup"], "uuid_public_token")
        self.assertFalse(consolidation_check["details"]["numeric_public_success_urls"])
        self.assertEqual(consolidation_check["details"]["medical_records"], "approved_patient_read_only")
        self.assertFalse(consolidation_check["details"]["public_medical_records"])
        self.assertFalse(prohibited_check["details"]["uploads_enabled"])
        self.assertFalse(prohibited_check["details"]["medical_records_enabled"])
        self.assertFalse(prohibited_check["details"]["whatsapp_api_enabled"])
        self.assertFalse(prohibited_check["details"]["payments_enabled"])
        self.assertFalse(prohibited_check["details"]["email_password_reset_enabled"])

    @override_settings(
        PRODUCTION=True,
        DEBUG=True,
        SECRET_KEY="change-me",
        ALLOWED_HOSTS=[],
        CSRF_TRUSTED_ORIGINS=[],
        BOOKING_TRUST_X_FORWARDED_FOR=False,
    )
    def test_strict_fails_when_production_like_requirements_are_missing(self):
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("deployment_smoke", strict=True, stdout=output)

        text = output.getvalue()
        self.assertIn("[FAIL]", text)
        self.assertIn("application secret", text)
        self.assertNotIn("SECRET_KEY", text)

    @ignore_warnings(message="Overriding setting DATABASES can lead to unexpected behavior.")
    @override_settings(
        PRODUCTION=True,
        DEBUG=True,
        SECRET_KEY="test-only-long-production-secret-placeholder",
        ALLOWED_HOSTS=["clinic.example.test"],
        CSRF_TRUSTED_ORIGINS=["https://clinic.example.test"],
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"}},
        SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
        SECURE_HSTS_SECONDS=0,
        BOOKING_TRUST_X_FORWARDED_FOR=True,
        BOOKING_TRUSTED_PROXY_CONFIGURED=False,
    )
    def test_strict_flags_production_like_infrastructure_and_https_blockers(self):
        output = StringIO()

        with self.assertRaises(CommandError):
            call_command("deployment_smoke", strict=True, stdout=output)

        text = output.getvalue()
        for expected in [
            "production_debug_disabled",
            "production_database_backend",
            "production_cache_backend",
            "production_https_redirect",
            "production_session_cookie_secure",
            "production_csrf_cookie_secure",
            "production_hsts",
            "production_booking_proxy_attestation",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertNotIn("DATABASE_URL", text)
        self.assertNotIn("CACHE_URL", text)
        self.assertNotIn("SECRET_KEY", text)

    def test_output_does_not_include_raw_secret_or_connection_values(self):
        output = StringIO()
        secret_value = "super-secret-smoke-value"
        database_value = "postgres://user:db-secret@example.test:5432/clinic"
        cache_value = "redis://:cache-secret@example.test:6379/1"

        with override_settings(SECRET_KEY=secret_value):
            with patch.dict(
                os.environ,
                {
                    "DJANGO_SECRET_KEY": secret_value,
                    "DATABASE_URL": database_value,
                    "CACHE_URL": cache_value,
                },
            ):
                call_command("deployment_smoke", stdout=output)

        text = output.getvalue()
        self.assertNotIn(secret_value, text)
        self.assertNotIn(database_value, text)
        self.assertNotIn(cache_value, text)
        self.assertNotIn("db-secret", text)
        self.assertNotIn("cache-secret", text)
        self.assertNotIn("SECRET_KEY", text)
        self.assertNotIn("DATABASE_URL", text)
        self.assertNotIn("CACHE_URL", text)

    def test_json_output_does_not_include_raw_secret_or_connection_values(self):
        output = StringIO()
        secret_value = "json-secret-value"
        database_value = "postgres://user:json-db-secret@example.test:5432/clinic"
        cache_value = "redis://:json-cache-secret@example.test:6379/1"

        with override_settings(SECRET_KEY=secret_value):
            with patch.dict(
                os.environ,
                {
                    "DJANGO_SECRET_KEY": secret_value,
                    "DATABASE_URL": database_value,
                    "CACHE_URL": cache_value,
                },
            ):
                call_command("deployment_smoke", json_output=True, stdout=output)

        text = output.getvalue()
        json.loads(text)
        self.assertNotIn(secret_value, text)
        self.assertNotIn(database_value, text)
        self.assertNotIn(cache_value, text)
        self.assertNotIn("json-db-secret", text)
        self.assertNotIn("json-cache-secret", text)
        self.assertNotIn("SECRET_KEY", text)
        self.assertNotIn("DATABASE_URL", text)
        self.assertNotIn("CACHE_URL", text)

    def test_output_does_not_include_patient_data_or_tokens(self):
        appointment = self.create_patient_appointment()

        human_output = self.call_smoke()
        json_output = self.call_smoke(json_output=True)
        combined = human_output + json_output
        json.loads(json_output)

        self.assertNotIn("Batch Ten Private Patient", combined)
        self.assertNotIn("private-patient@example.test", combined)
        self.assertNotIn("0799999999", combined)
        self.assertNotIn("+962799999999", combined)
        self.assertNotIn(str(appointment.public_token), combined)
        self.assertNotIn(appointment.confirmation_reference, combined)

    def test_database_failure_is_reported_without_exception_details(self):
        output = StringIO()

        with patch(
            "apps.core.management.commands.deployment_smoke.connection.ensure_connection",
            side_effect=Exception("password=raw-secret"),
        ):
            with self.assertRaises(CommandError):
                call_command("deployment_smoke", stdout=output)

        text = output.getvalue()
        self.assertIn("Database connectivity failed", text)
        self.assertNotIn("raw-secret", text)
        self.assertNotIn("password=raw-secret", text)

    def test_cache_failure_is_reported_without_backend_url_details(self):
        output = StringIO()

        with patch(
            "apps.core.management.commands.deployment_smoke.cache.set",
            side_effect=Exception("redis://:raw-cache-secret@example.test:6379/1"),
        ):
            with self.assertRaises(CommandError):
                call_command("deployment_smoke", stdout=output)

        text = output.getvalue()
        self.assertIn("Default cache check failed", text)
        self.assertNotIn("raw-cache-secret", text)
        self.assertNotIn("redis://", text)


class ProjectStatusReportCommandTests(TestCase):
    def call_report(self, **options):
        output = StringIO()
        call_command("project_status_report", stdout=output, **options)
        return output.getvalue()

    def create_private_records(self):
        user = get_user_model().objects.create_user(
            username="+962788888888",
            email="status-private@example.test",
            password="test-password",
            first_name="Status Private",
        )
        doctor = Doctor.objects.create(
            full_name_ar="ط®ط§ظ„ط¯ ط­ط³ط§ظ† ط¨ط¯ط±ط§ظ†",
            full_name_en="Khaled Hassan Badran",
            title_en="Dr.",
            is_active=True,
        )
        visit_type = VisitType.objects.create(
            doctor=doctor,
            name_ar="ظƒط´ظپ",
            name_en="Status Visit",
            duration_minutes=30,
            is_active=True,
        )
        patient = Patient.objects.create(
            user=user,
            full_name="Status Private Patient",
            phone_raw="0788888888",
            phone_e164="+962788888888",
        )
        starts_at = timezone.now() + timedelta(days=1)
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
        )

    def assert_private_values_absent(self, text, appointment):
        self.assertNotIn("Status Private Patient", text)
        self.assertNotIn("status-private@example.test", text)
        self.assertNotIn("0788888888", text)
        self.assertNotIn("+962788888888", text)
        self.assertNotIn(str(appointment.public_token), text)
        self.assertNotIn(appointment.confirmation_reference, text)

    def test_text_output_is_counts_only_and_safe(self):
        appointment = self.create_private_records()

        text = self.call_report()

        self.assertIn("Project status report for Dr. Khaled Badran Clinic", text)
        self.assertIn("patients=1", text)
        self.assertIn("appointments=1", text)
        self.assertIn("public_success_lookup=uuid_public_token", text)
        self.assertIn("uploads=False", text)
        self.assertIn("medical_records=True", text)
        self.assertIn("patient_approved_medical_records=True", text)
        self.assertIn("public_medical_records=False", text)
        self.assertIn("whatsapp_api_or_webhook=False", text)
        self.assertIn("payments=False", text)
        self.assert_private_values_absent(text, appointment)

    def test_json_output_is_counts_only_and_safe(self):
        appointment = self.create_private_records()

        text = self.call_report(json_output=True)
        payload = json.loads(text)

        self.assertEqual(payload["command"], "project_status_report")
        self.assertEqual(payload["counts"]["patients"], 1)
        self.assertEqual(payload["counts"]["appointments"], 1)
        self.assertEqual(payload["security"]["public_success_lookup"], "uuid_public_token")
        self.assertFalse(payload["features"]["uploads"])
        self.assertTrue(payload["features"]["medical_records"])
        self.assertTrue(payload["features"]["patient_approved_medical_records"])
        self.assertFalse(payload["features"]["public_medical_records"])
        self.assertFalse(payload["features"]["public_medical_file_urls"])
        self.assertFalse(payload["features"]["whatsapp_api_or_webhook"])
        self.assertFalse(payload["features"]["payments"])
        self.assertFalse(payload["security"]["prohibited_features"]["uploads_enabled"])
        self.assert_private_values_absent(text, appointment)


class ProductionSettingsReportCommandTests(SimpleTestCase):
    def call_report(self, **options):
        output = StringIO()
        call_command("production_settings_report", stdout=output, **options)
        return output.getvalue()

    def assert_sensitive_values_absent(self, text):
        blocked_values = [
            "report-secret-value",
            "postgres://report-user:report-password@example.test:5432/clinic",
            "redis://:report-cache-password@example.test:6379/1",
            "report-password",
            "report-cache-password",
            "DJANGO_SECRET_KEY",
            "SECRET_KEY",
            "DATABASE_URL",
            "CACHE_URL",
        ]
        for value in blocked_values:
            with self.subTest(value=value):
                self.assertNotIn(value, text)

    @ignore_warnings(message="Overriding setting DATABASES can lead to unexpected behavior.")
    @override_settings(
        SECRET_KEY="report-secret-value",
        PRODUCTION=True,
        DEBUG=False,
        ALLOWED_HOSTS=["clinic.example.test"],
        CSRF_TRUSTED_ORIGINS=["https://clinic.example.test"],
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "clinic"}},
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "redis://:report-cache-password@example.test:6379/1",
            }
        },
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=3600,
        SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    )
    def test_text_output_reports_categories_without_sensitive_values(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_SECRET_KEY": "report-secret-value",
                "DATABASE_URL": "postgres://report-user:report-password@example.test:5432/clinic",
                "CACHE_URL": "redis://:report-cache-password@example.test:6379/1",
            },
        ):
            text = self.call_report()

        self.assertIn("Production settings report", text)
        self.assertIn("database=postgresql", text)
        self.assertIn("cache=redis", text)
        self.assertIn("allowed_hosts_count=1", text)
        self.assertIn("csrf_trusted_origins_count=1", text)
        self.assertIn("session_cookie_secure=True", text)
        self.assert_sensitive_values_absent(text)

    @ignore_warnings(message="Overriding setting DATABASES can lead to unexpected behavior.")
    @override_settings(
        SECRET_KEY="report-secret-value",
        PRODUCTION=True,
        DEBUG=False,
        ALLOWED_HOSTS=["clinic.example.test"],
        CSRF_TRUSTED_ORIGINS=["https://clinic.example.test"],
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "clinic"}},
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "redis://:report-cache-password@example.test:6379/1",
            }
        },
        SECURE_SSL_REDIRECT=True,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=3600,
    )
    def test_json_output_reports_categories_without_sensitive_values(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_SECRET_KEY": "report-secret-value",
                "DATABASE_URL": "postgres://report-user:report-password@example.test:5432/clinic",
                "CACHE_URL": "redis://:report-cache-password@example.test:6379/1",
            },
        ):
            text = self.call_report(json_output=True)

        payload = json.loads(text)
        self.assertEqual(payload["command"], "production_settings_report")
        self.assertTrue(payload["production_like"])
        self.assertFalse(payload["debug"])
        self.assertEqual(payload["database_backend"], "postgresql")
        self.assertEqual(payload["cache_backend"], "redis")
        self.assertEqual(payload["allowed_hosts_count"], 1)
        self.assertEqual(payload["csrf_trusted_origins_count"], 1)
        self.assertTrue(payload["session_cookie_secure"])
        self.assert_sensitive_values_absent(text)


class OperationalDocumentationTests(SimpleTestCase):
    docs_dir = Path(settings.BASE_DIR) / "docs"
    scripts_dir = Path(settings.BASE_DIR) / "scripts"

    def read_doc(self, name):
        return (self.docs_dir / name).read_text(encoding="utf-8")

    def read_script(self, name):
        return (self.scripts_dir / name).read_text(encoding="utf-8")

    def test_batch_7_runbook_documents_exist(self):
        expected_docs = [
            "BACKUP_RESTORE_RUNBOOK.md",
            "INCIDENT_RESPONSE_RUNBOOK.md",
            "RELEASE_CHECKLIST.md",
            "LOAD_TEST_PLAN.md",
            "SECURITY_REGRESSION_CHECKLIST.md",
            "BATCH_7_STATUS.md",
        ]

        for doc_name in expected_docs:
            with self.subTest(doc_name=doc_name):
                self.assertTrue((self.docs_dir / doc_name).exists())

    def test_environment_doc_defines_local_staging_and_production(self):
        content = self.read_doc("ENVIRONMENT.md")

        self.assertIn("Local development", content)
        self.assertIn("Staging", content)
        self.assertIn("Production", content)
        self.assertIn("config.settings.prod", content)
        self.assertIn("PostgreSQL", content)
        self.assertIn("Redis", content)
        self.assertIn("must not contain real patient data", content)

    def test_new_operational_docs_are_linked_from_readme_and_production_readiness(self):
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")
        production_readiness = self.read_doc("PRODUCTION_READINESS.md")
        expected_links = [
            "BACKUP_RESTORE_RUNBOOK.md",
            "INCIDENT_RESPONSE_RUNBOOK.md",
            "RELEASE_CHECKLIST.md",
            "LOAD_TEST_PLAN.md",
            "SECURITY_REGRESSION_CHECKLIST.md",
        ]

        for link in expected_links:
            with self.subTest(link=link):
                self.assertIn(link, readme)
                self.assertIn(link, production_readiness)

    def test_release_checklist_contains_portal_foundation_safety_gates(self):
        content = self.read_doc("RELEASE_CHECKLIST.md")

        self.assertIn("patient portal remains bounded to account security, linked-appointment", content)
        self.assertIn("logged-in password change uses Django validation/hashing", content)
        self.assertIn("account recovery is clinic-assisted", content)
        self.assertIn("no patient-facing uploads until private media design", content)
        self.assertIn("no WhatsApp until consent/logging/cost/security design exists", content)
        self.assertIn("patient-facing medical records are limited to read-only doctor/staff-approved", content)

    def test_ci_workflow_runs_deployment_smoke(self):
        workflow = Path(settings.BASE_DIR, ".github", "workflows", "django.yml").read_text(encoding="utf-8")

        self.assertIn("python manage.py makemigrations --check --dry-run", workflow)
        self.assertIn("python manage.py check --deploy", workflow)
        self.assertIn("python manage.py deployment_smoke", workflow)
        self.assertIn("python manage.py deployment_smoke --json", workflow)
        self.assertIn("python manage.py project_status_report", workflow)
        self.assertIn("python manage.py project_status_report --json", workflow)
        self.assertIn("python manage.py production_settings_report", workflow)
        self.assertIn("python manage.py production_settings_report --json", workflow)
        self.assertIn("python manage.py test", workflow)

    def test_batch_10_consolidation_documents_exist_and_are_linked(self):
        expected_docs = [
            "PROJECT_MAP.md",
            "ROUTE_ACCESS_MATRIX.md",
            "DATA_EXPOSURE_MATRIX.md",
            "STAGING_VALIDATION_PLAN.md",
            "FIGMA_DESIGN_HANDOFF.md",
            "PROJECT_RELEASE_SCORECARD.md",
            "BATCH_10_STATUS.md",
            "BATCH_10_PROGRESS.md",
        ]
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")

        for doc_name in expected_docs:
            with self.subTest(doc_name=doc_name):
                self.assertTrue((self.docs_dir / doc_name).exists())
                if doc_name not in {"BATCH_10_PROGRESS.md"}:
                    self.assertIn(doc_name, readme)

    def test_route_access_and_data_exposure_docs_cover_security_boundaries(self):
        route_matrix = self.read_doc("ROUTE_ACCESS_MATRIX.md")
        data_matrix = self.read_doc("DATA_EXPOSURE_MATRIX.md")

        for expected in [
            "/book/success/<uuid:public_token>/",
            "/staff/appointments/<appointment-id>/cancel/",
            "/portal/appointments/<uuid:public_token>/",
            "/whatsapp/api/",
            "/portal/payments/",
            "CSRF expectation",
            "never_cache",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, route_matrix)

        for expected in [
            "Patient-safe fields visible in the patient portal",
            "Booking success must not expose",
            "Never on Patient Pages",
            "status history notes",
            "WhatsApp must not carry detailed medical information",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, data_matrix)

    def test_staging_plan_documents_production_like_prerequisites(self):
        content = self.read_doc("STAGING_VALIDATION_PLAN.md")

        for expected in [
            "PostgreSQL required",
            "Redis or another shared Django cache required",
            "DEBUG=False",
            "No real patient data",
            "deployment_smoke --strict",
            "project_status_report --json",
            "backup/restore drill",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, content)

    def test_figma_handoff_rule_is_documented_without_bypassing_security(self):
        figma_doc = self.read_doc("FIGMA_DESIGN_HANDOFF.md")
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")
        security = self.read_doc("SECURITY_HARDENING.md")

        self.assertIn("Codex does not design", figma_doc)
        self.assertIn("Figma is the source of truth", figma_doc)
        self.assertIn("Design approval cannot bypass security", readme)
        self.assertIn("Design Governance and Security", security)

    def test_project_status_report_is_documented_as_safe(self):
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")
        project_map = self.read_doc("PROJECT_MAP.md")
        security_checklist = self.read_doc("SECURITY_REGRESSION_CHECKLIST.md")

        self.assertIn("python manage.py project_status_report", readme)
        self.assertIn("project_status_report", project_map)
        self.assertIn("do not print patient names", security_checklist)

    def test_batch_11_validation_scripts_exist_and_are_linked_from_readme(self):
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")
        expected_scripts = [
            "validate_local_release.ps1",
            "validate_local_release.sh",
            "validate_staging_env.ps1",
            "validate_staging_env.sh",
        ]

        for script_name in expected_scripts:
            with self.subTest(script_name=script_name):
                self.assertTrue((self.scripts_dir / script_name).exists())
                self.assertIn(f"scripts/{script_name}", readme)

    def test_batch_11_operational_documents_exist_and_are_linked(self):
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")
        project_map = self.read_doc("PROJECT_MAP.md")
        expected_docs = [
            "STAGING_GAP_ANALYSIS.md",
            "STAGING_ENVIRONMENT_CONTRACT.md",
            "LOCAL_STAGING_SIMULATION.md",
            "POSTGRESQL_READINESS.md",
            "REDIS_RATE_LIMIT_READINESS.md",
            "BACKUP_RESTORE_DRILL.md",
            "MONITORING_ALERTING_READINESS.md",
            "DEPENDENCY_SECURITY_READINESS.md",
            "STAFF_ACCESS_GOVERNANCE.md",
            "LEGAL_PRIVACY_OPERATIONS.md",
            "BATCH_11_PROGRESS.md",
            "BATCH_11_STATUS.md",
        ]

        for doc_name in expected_docs:
            with self.subTest(doc_name=doc_name):
                self.assertTrue((self.docs_dir / doc_name).exists())
                self.assertIn(doc_name, project_map)
                if doc_name not in {"BATCH_11_PROGRESS.md"}:
                    self.assertIn(doc_name, readme)

    def test_batch_11_validation_scripts_do_not_contain_real_looking_secrets(self):
        secret_patterns = [
            r"sk-[A-Za-z0-9_-]{20,}",
            r"ghp_[A-Za-z0-9_]{20,}",
            r"xox[baprs]-[A-Za-z0-9-]{20,}",
            r"AKIA[0-9A-Z]{16}",
            r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
            r"postgres://[^:\s]+:[^@\s]+@",
            r"redis://:[^@\s]+@",
        ]

        for script_path in self.scripts_dir.glob("validate_*"):
            content = script_path.read_text(encoding="utf-8")
            for pattern in secret_patterns:
                with self.subTest(script=script_path.name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, content))

    def test_batch_11_validation_scripts_do_not_run_source_control_or_publish_actions(self):
        forbidden_command_patterns = [
            r"\bgit\s+push\b",
            r"\bgit\s+commit\b",
            r"\bgit\s+merge\b",
            r"\bgit\s+reset\b",
            r"\bgit\s+checkout\b",
            r"\bdocker\s+push\b",
            r"\bterraform\s+apply\b",
            r"\bkubectl\s+apply\b",
            r"\bgcloud\s+app\s+deploy\b",
            r"\bfly\s+deploy\b",
            r"\bvercel\b",
            r"\bnetlify\s+deploy\b",
            r"\bheroku\b",
        ]

        for script_path in self.scripts_dir.glob("validate_*"):
            content = script_path.read_text(encoding="utf-8").lower()
            for pattern in forbidden_command_patterns:
                with self.subTest(script=script_path.name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, content))

    def test_local_staging_simulation_compose_is_local_only_and_documented(self):
        compose_path = Path(settings.BASE_DIR, "docker-compose.staging-validation.yml")
        local_simulation_doc = self.read_doc("LOCAL_STAGING_SIMULATION.md")
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")

        self.assertTrue(compose_path.exists())
        self.assertIn("docker-compose.staging-validation.yml", local_simulation_doc)
        self.assertIn("LOCAL_STAGING_SIMULATION.md", readme)

    def test_local_staging_simulation_compose_has_no_real_looking_secrets(self):
        compose = Path(settings.BASE_DIR, "docker-compose.staging-validation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("local_validation_password", compose)
        self.assertNotIn("replace-with-db-password", compose)

        secret_patterns = [
            r"sk-[A-Za-z0-9_-]{20,}",
            r"ghp_[A-Za-z0-9_]{20,}",
            r"AKIA[0-9A-Z]{16}",
            r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
        ]
        for pattern in secret_patterns:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, compose))

    def test_local_staging_simulation_compose_does_not_bind_public_interfaces(self):
        compose = Path(settings.BASE_DIR, "docker-compose.staging-validation.yml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("0.0.0.0:", compose)
        self.assertNotIn('"5432:5432"', compose)
        self.assertNotIn('"6379:6379"', compose)
        self.assertIn("127.0.0.1:54329:5432", compose)
        self.assertIn("127.0.0.1:63790:6379", compose)

    def test_dependabot_config_is_bounded_and_secret_free(self):
        dependabot_path = Path(settings.BASE_DIR, ".github", "dependabot.yml")
        content = dependabot_path.read_text(encoding="utf-8")
        readme = Path(settings.BASE_DIR, "README.md").read_text(encoding="utf-8")
        dependency_doc = self.read_doc("DEPENDENCY_SECURITY_READINESS.md")

        self.assertTrue(dependabot_path.exists())
        self.assertIn('package-ecosystem: "pip"', content)
        self.assertIn('package-ecosystem: "github-actions"', content)
        self.assertNotIn("auto-merge", content.lower())
        self.assertNotIn("token", content.lower())
        self.assertNotIn("password", content.lower())
        self.assertNotIn("secret", content.lower())
        self.assertIn("DEPENDENCY_SECURITY_READINESS.md", readme)
        self.assertIn("Do not auto-merge", dependency_doc)


class PortalFoundationRouteTests(TestCase):
    def test_patient_portal_requires_authentication(self):
        response = self.client.get("/portal/")

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_upload_whatsapp_and_unscoped_medical_record_routes_remain_absent(self):
        blocked_paths = [
            "/uploads/",
            "/portal/uploads/",
            "/whatsapp/webhook/",
            "/api/whatsapp/",
            "/whatsapp/api/",
            "/records/",
            "/medical-records/",
            "/payments/",
            "/portal/payments/",
        ]

        for path in blocked_paths:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 404)

    def test_patient_medical_records_route_requires_authentication(self):
        response = self.client.get("/portal/medical-records/")

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])


class PublicCasesTestDataMixin:
    @classmethod
    def setUpClass(cls):
        cls._private_media_tempdir = TemporaryDirectory()
        cls._private_media_override = override_settings(
            PRIVATE_MEDIA_ROOT=Path(cls._private_media_tempdir.name)
        )
        cls._private_media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._private_media_override.disable()
        cls._private_media_tempdir.cleanup()

    def synthetic_image_file(self, name="synthetic-public-case.jpg", content=b"public-image-bytes"):
        return SimpleUploadedFile(name, content, content_type="image/jpeg")

    def synthetic_video_file(self, name="synthetic-public-case.mp4", content=b"public-video-bytes"):
        return SimpleUploadedFile(name, content, content_type="video/mp4")

    def create_patient(
        self,
        *,
        user=None,
        full_name="Synthetic Patient",
        phone_raw="0790000101",
        phone_e164="+962790000101",
    ):
        return Patient.objects.create(
            user=user,
            full_name=full_name,
            phone_raw=phone_raw,
            phone_e164=phone_e164,
            date_of_birth=date(1990, 1, 1),
        )

    def create_visit(self, *, patient, **kwargs):
        defaults = {
            "patient": patient,
            "visit_reason": "Private visit reason hidden from public cases.",
            "doctor_notes": "Private doctor notes hidden from public cases.",
            "diagnosis_plan": "Private diagnosis plan hidden from public cases.",
            "instructions": "Private instructions hidden from public cases.",
            "follow_up_notes": "Private follow-up notes hidden from public cases.",
            "is_visible_to_patient": True,
        }
        defaults.update(kwargs)
        return VisitRecord.objects.create(**defaults)

    def create_appointment(self, *, patient):
        doctor = Doctor.objects.create(
            full_name_ar="Synthetic Private Appointment Doctor",
            full_name_en="Synthetic Private Appointment Doctor",
            title_en="Dr.",
            is_active=False,
        )
        visit_type = VisitType.objects.create(
            doctor=doctor,
            name_ar="Synthetic Private Appointment Type",
            name_en="Synthetic Private Appointment Type",
            duration_minutes=30,
            is_active=False,
        )
        starts_at = timezone.now() + timedelta(days=1)
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            booking_note="Private appointment booking note hidden from public cases.",
        )

    def create_public_case(
        self,
        *,
        patient=None,
        reference_visit=None,
        title="",
        note="",
        detail_note="",
        consent_confirmed=True,
        is_published=True,
    ):
        patient = patient or (reference_visit.patient if reference_visit else self.create_patient())
        return PublicCase.objects.create(
            patient=patient,
            reference_visit=reference_visit,
            title=title,
            note=note,
            detail_note=detail_note,
            consent_confirmed=consent_confirmed,
            is_published=is_published,
        )

    def create_media(
        self,
        *,
        patient=None,
        visit=None,
        folder=None,
        public_case=None,
        public_case_role=None,
        media_type=RecordMedia.MediaType.IMAGE,
        visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
        consent_confirmed=None,
        is_active=True,
        title="Synthetic approved public case media",
        description="Synthetic approved public case description.",
        file=None,
    ):
        patient = patient or self.create_patient()
        if file is None:
            file = (
                self.synthetic_video_file()
                if media_type == RecordMedia.MediaType.SHORT_VIDEO
                else self.synthetic_image_file()
            )
        if consent_confirmed is None:
            consent_confirmed = visibility == RecordMedia.Visibility.APPROVED_PUBLIC_CASE
        if visibility == RecordMedia.Visibility.APPROVED_PUBLIC_CASE:
            if public_case is None:
                if visit is not None:
                    public_case = PublicCase.objects.filter(
                        patient=patient,
                        reference_visit=visit,
                    ).first()
                if public_case is None:
                    public_case = PublicCase.objects.create(
                        patient=patient,
                        reference_visit=visit,
                        consent_confirmed=True,
                        is_published=True,
                    )
            if public_case_role is None:
                decoded_role = decode_public_case_title(title)[0]
                if media_type == RecordMedia.MediaType.SHORT_VIDEO:
                    public_case_role = RecordMedia.PublicCaseRole.VIDEO
                elif decoded_role in {
                    RecordMedia.PublicCaseRole.BEFORE,
                    RecordMedia.PublicCaseRole.AFTER,
                    RecordMedia.PublicCaseRole.VIDEO_COVER,
                }:
                    public_case_role = decoded_role
                else:
                    public_case_role = RecordMedia.PublicCaseRole.PRIMARY
        return RecordMedia.objects.create(
            patient=patient,
            visit=visit,
            folder=folder,
            public_case=public_case,
            public_case_role=public_case_role or "",
            media_type=media_type,
            file=file,
            visibility=visibility,
            consent_confirmed=consent_confirmed,
            is_active=is_active,
            title=title,
            description=description,
        )

    def force_unconsented_public_case(self, media):
        if connection.vendor != "sqlite":
            self.skipTest("Unconsented approved_public_case rows are blocked by the database constraint.")
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA ignore_check_constraints = ON")
        try:
            RecordMedia.objects.filter(pk=media.pk).update(consent_confirmed=False)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("PRAGMA ignore_check_constraints = OFF")
        media.refresh_from_db()
        return media


class PublicCasesPageTests(PublicCasesTestDataMixin, TestCase):
    def test_public_cases_routes_return_200_without_login(self):
        for route_name in ["public_cases", "public_cases_en"]:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)

    def test_empty_state_is_safe(self):
        response = self.client.get(reverse("public_cases_en"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only cases explicitly approved for public display are shown.", count=1)
        self.assertContains(response, "No public cases are currently published.", count=1)
        self.assertNotContains(response, "outcome guarantee")
        self.assertNotContains(response, "Patient-visible portal media")
        self.assertNotContains(response, "<form")
        self.assertNotContains(response, "upload")
        self.assertNotContains(response, str(settings.PRIVATE_MEDIA_ROOT))

    def test_only_approved_consented_active_public_case_media_appears(self):
        approved_image_case = self.create_public_case(
            title="Approved public image case",
            note="Image publication note.",
        )
        approved_image = self.create_media(
            patient=approved_image_case.patient,
            public_case=approved_image_case,
            title="INTERNAL-IMAGE-TITLE-MUST-STAY-HIDDEN",
            description="INTERNAL-IMAGE-DESCRIPTION-MUST-STAY-HIDDEN",
            file=self.synthetic_image_file(name="synthetic-public-case.jpg"),
        )
        approved_video_case = self.create_public_case(
            title="Approved public video case",
            note="Video publication note.",
        )
        approved_video = self.create_media(
            patient=approved_video_case.patient,
            public_case=approved_video_case,
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            title="INTERNAL-VIDEO-TITLE-MUST-STAY-HIDDEN",
            description="INTERNAL-VIDEO-DESCRIPTION-MUST-STAY-HIDDEN",
            file=self.synthetic_video_file(name="synthetic-public-case.mp4"),
        )
        self.create_media(
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
            title="Private-only media must stay hidden",
        )
        self.create_media(
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Patient-visible media must stay hidden",
        )
        self.create_media(
            is_active=False,
            title="Inactive public case media must stay hidden",
        )
        unconsented = self.create_media(title="Unconsented public case media must stay hidden")
        self.force_unconsented_public_case(unconsented)

        response = self.client.get(reverse("public_cases_en"))

        self.assertContains(response, approved_image_case.title, count=1)
        self.assertContains(response, approved_image_case.note, count=1)
        self.assertContains(response, approved_video_case.title, count=1)
        self.assertContains(response, approved_video_case.note, count=1)
        self.assertContains(
            response,
            f'src="{reverse("public_case_media_en", kwargs={"public_id": approved_image.public_id})}"',
        )
        self.assertContains(
            response,
            f'data-src="{reverse("public_case_media_en", kwargs={"public_id": approved_video.public_id})}"',
        )
        self.assertNotContains(response, "Private-only media must stay hidden")
        self.assertNotContains(response, "Patient-visible media must stay hidden")
        self.assertNotContains(response, "Inactive public case media must stay hidden")
        self.assertNotContains(response, "Unconsented public case media must stay hidden")
        self.assertNotContains(response, "INTERNAL-IMAGE-TITLE-MUST-STAY-HIDDEN")
        self.assertNotContains(response, "INTERNAL-IMAGE-DESCRIPTION-MUST-STAY-HIDDEN")
        self.assertNotContains(response, "INTERNAL-VIDEO-TITLE-MUST-STAY-HIDDEN")
        self.assertNotContains(response, "INTERNAL-VIDEO-DESCRIPTION-MUST-STAY-HIDDEN")
        self.assertNotContains(response, approved_image.file.name)
        self.assertNotContains(response, approved_video.file.name)
        self.assertNotContains(response, "synthetic-public-case.jpg")
        self.assertNotContains(response, "synthetic-public-case.mp4")
        self.assertNotContains(response, str(settings.PRIVATE_MEDIA_ROOT))
        self.assertNotContains(response, 'href="/media/')

    def test_public_cases_page_does_not_expose_patient_identity_or_private_record_content(self):
        patient = self.create_patient(
            full_name="Synthetic Patient Hidden Identity",
            phone_raw="0790000111",
            phone_e164="+962790000111",
        )
        appointment = self.create_appointment(patient=patient)
        visit = self.create_visit(patient=patient, appointment=appointment)
        ClinicalNote.objects.create(
            patient=patient,
            visit=visit,
            title="Private clinical note title hidden from public cases",
            body="Private clinical note body hidden from public cases.",
            is_visible_to_patient=True,
        )
        folder = RecordMediaFolder.objects.create(
            patient=patient,
            name="PRIVATE-FOLDER-NAME-MUST-STAY-HIDDEN",
        )
        public_case = self.create_public_case(
            patient=patient,
            reference_visit=visit,
            title="Approved explicit public case title",
            note="Approved explicit public case note.",
        )
        media = self.create_media(
            patient=patient,
            visit=visit,
            folder=folder,
            public_case=public_case,
            title="INTERNAL-RECORD-MEDIA-TITLE-MUST-STAY-HIDDEN",
            description="INTERNAL-RECORD-MEDIA-NOTE-MUST-STAY-HIDDEN",
        )

        response = self.client.get(reverse("public_cases_en"))

        self.assertContains(response, public_case.title, count=1)
        self.assertContains(response, public_case.note, count=1)
        blocked_fragments = [
            patient.full_name,
            patient.phone_raw,
            patient.phone_e164,
            "1990",
            appointment.booking_note,
            appointment.visit_type.name_en,
            visit.visit_reason,
            visit.doctor_notes,
            visit.diagnosis_plan,
            visit.instructions,
            visit.follow_up_notes,
            "Private clinical note title hidden from public cases",
            "Private clinical note body hidden from public cases.",
            folder.name,
            media.title,
            media.description,
            media.file.name,
            str(settings.PRIVATE_MEDIA_ROOT),
        ]
        for fragment in blocked_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotContains(response, fragment)

    def test_before_after_video_group_renders_once_with_one_note_and_neutral_heading(self):
        patient = self.create_patient(
            full_name="Synthetic Grouped Case Hidden Patient",
            phone_raw="0790000222",
            phone_e164="+962790000222",
        )
        appointment = self.create_appointment(patient=patient)
        visit = self.create_visit(patient=patient, appointment=appointment)
        note = "Synthetic explicit short public case note."
        detail_note = (
            "Synthetic complete detailed case note.\n"
            "This text belongs only to the final case-note slide."
        )
        public_case = self.create_public_case(
            patient=patient,
            reference_visit=visit,
            note=note,
            detail_note=detail_note,
        )
        before = self.create_media(
            patient=patient,
            visit=visit,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
            title="Before",
            description="INTERNAL-BEFORE-NOTE-MUST-STAY-HIDDEN",
            file=self.synthetic_image_file(name="synthetic-before.jpg"),
        )
        after = self.create_media(
            patient=patient,
            visit=visit,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.AFTER,
            title="After",
            description="INTERNAL-AFTER-NOTE-MUST-STAY-HIDDEN",
            file=self.synthetic_image_file(name="synthetic-after.jpg"),
        )
        video = self.create_media(
            patient=patient,
            visit=visit,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.VIDEO,
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            title="Video",
            description="INTERNAL-VIDEO-NOTE-MUST-STAY-HIDDEN",
            file=self.synthetic_video_file(name="synthetic-case.mp4"),
        )

        response = self.client.get(reverse("public_cases_en"))
        content = response.content.decode()
        before_url = reverse("public_case_media_en", kwargs={"public_id": before.public_id})
        after_url = reverse("public_case_media_en", kwargs={"public_id": after.public_id})
        video_url = reverse("public_case_media_en", kwargs={"public_id": video.public_id})

        self.assertContains(response, 'class="public-case-card public-case-album-card"', count=1)
        self.assertContains(response, "Authorized case 1", count=1)
        self.assertContains(response, note, count=1)
        self.assertContains(response, detail_note, count=1)
        self.assertContains(
            response,
            reverse("public_case_detail_en", kwargs={"case_id": public_case.pk}),
        )
        self.assertNotContains(response, "INTERNAL-BEFORE-NOTE-MUST-STAY-HIDDEN")
        self.assertNotContains(response, "INTERNAL-AFTER-NOTE-MUST-STAY-HIDDEN")
        self.assertNotContains(response, "INTERNAL-VIDEO-NOTE-MUST-STAY-HIDDEN")
        self.assertEqual(content.count(f'src="{before_url}"'), 1)
        self.assertEqual(content.count(f'src="{after_url}"'), 1)
        self.assertEqual(content.count(f'data-src="{video_url}"'), 1)
        self.assertContains(response, 'data-slide-label="Before 1 of 1"', count=1)
        self.assertContains(response, 'data-slide-label="After 1 of 1"', count=1)
        self.assertContains(response, 'data-slide-label="Video 1 of 1"', count=1)
        self.assertContains(response, 'data-slide-label="Case Notes"', count=1)
        self.assertContains(response, 'data-slide-kind="note"', count=1)
        self.assertContains(response, "data-case-note-text", count=1)
        self.assertContains(response, "1 / 4", count=1)
        note_slide = re.search(
            r'<figure\s+class="public-case-carousel-slide public-case-carousel-note-slide"(?P<body>.*?)</figure>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(note_slide)
        self.assertNotIn("data-media-public-id", note_slide.group("body"))
        self.assertNotIn("data-media-url", note_slide.group("body"))
        self.assertNotIn("<img", note_slide.group("body"))
        self.assertNotIn("<video", note_slide.group("body"))
        self.assertNotIn(note, note_slide.group("body"))
        self.assertContains(response, "data-case-controls", count=1)
        self.assertContains(response, "data-case-current-label", count=1)
        self.assertContains(response, "data-case-counter", count=1)
        self.assertNotIn("public-case-image-grid", content)
        self.assertNotIn("public-case-video-grid", content)

        detail = self.client.get(
            reverse("public_case_detail_en", kwargs={"case_id": public_case.pk})
        )
        detail_content = detail.content.decode()
        video_tag = re.search(r"<video[^>]*>", detail_content).group(0)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Authorized case 1", count=1)
        self.assertContains(detail, note, count=1)
        self.assertContains(detail, "Case Notes", count=1)
        for detail_line in detail_note.splitlines():
            self.assertContains(detail, detail_line, count=1)
        self.assertEqual(detail_content.count(f'src="{before_url}"'), 1)
        self.assertEqual(detail_content.count(f'src="{after_url}"'), 1)
        self.assertEqual(detail_content.count(f'src="{video_url}"'), 1)
        self.assertEqual(detail_content.count("<video"), 1)
        for attribute in ("muted", "playsinline", "controls"):
            self.assertIn(attribute, video_tag)
        self.assertNotIn("autoplay", video_tag)

        home = self.client.get(reverse("home_en"))
        self.assertContains(home, note, count=1)
        self.assertNotContains(home, detail_note)

        blocked_fragments = (
            patient.full_name,
            patient.phone_raw,
            patient.phone_e164,
            appointment.booking_note,
            visit.visit_reason,
            visit.doctor_notes,
            visit.diagnosis_plan,
            visit.instructions,
            visit.follow_up_notes,
            before.file.name,
            after.file.name,
            video.file.name,
            str(settings.PRIVATE_MEDIA_ROOT),
            'href="/media/',
        )
        for fragment in blocked_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotContains(response, fragment)

    def test_before_only_and_after_only_are_each_rendered_without_duplication(self):
        patient = self.create_patient(
            full_name="Synthetic Optional Role Hidden Patient",
            phone_raw="0790000444",
            phone_e164="+962790000444",
        )
        before_visit = self.create_visit(patient=patient)
        after_visit = self.create_visit(patient=patient)
        before_case = self.create_public_case(
            patient=patient,
            reference_visit=before_visit,
            note="Synthetic before-only note.",
        )
        after_case = self.create_public_case(
            patient=patient,
            reference_visit=after_visit,
            note="Synthetic after-only note.",
        )
        before = self.create_media(
            patient=patient,
            visit=before_visit,
            public_case=before_case,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
            title="Before",
            description="INTERNAL-BEFORE-ONLY-NOTE",
        )
        after = self.create_media(
            patient=patient,
            visit=after_visit,
            public_case=after_case,
            public_case_role=RecordMedia.PublicCaseRole.AFTER,
            title="After",
            description="INTERNAL-AFTER-ONLY-NOTE",
        )

        response = self.client.get(reverse("public_cases_en"))
        content = response.content.decode()
        before_url = reverse("public_case_media_en", kwargs={"public_id": before.public_id})
        after_url = reverse("public_case_media_en", kwargs={"public_id": after.public_id})

        self.assertEqual(content.count(f'src="{before_url}"'), 1)
        self.assertEqual(content.count(f'src="{after_url}"'), 1)
        self.assertContains(response, "Synthetic before-only note.", count=1)
        self.assertContains(response, "Synthetic after-only note.", count=1)
        self.assertNotContains(response, "INTERNAL-BEFORE-ONLY-NOTE")
        self.assertNotContains(response, "INTERNAL-AFTER-ONLY-NOTE")
        self.assertContains(response, 'class="public-case-card public-case-album-card"', count=2)
        self.assertContains(response, "data-case-carousel", count=2)
        self.assertNotContains(response, "data-case-controls")
        self.assertNotContains(response, 'class="public-case-image-grid"')
        before_detail = self.client.get(
            reverse("public_case_detail_en", kwargs={"case_id": before_case.pk})
        )
        after_detail = self.client.get(
            reverse("public_case_detail_en", kwargs={"case_id": after_case.pk})
        )
        self.assertContains(before_detail, 'class="public-case-image-grid"', count=1)
        self.assertContains(after_detail, 'class="public-case-image-grid"', count=1)

    def test_full_case_renders_all_assets_once_with_cover_and_home_remains_concise(self):
        patient = self.create_patient(
            full_name="Synthetic Multi Asset Hidden Patient",
            phone_raw="0790000666",
            phone_e164="+962790000666",
        )
        reference_visit = self.create_visit(patient=patient)
        before_visit = self.create_visit(patient=patient)
        after_visit = self.create_visit(patient=patient)
        video_visit = self.create_visit(patient=patient)
        folder = RecordMediaFolder.objects.create(
            patient=patient,
            name="INTERNAL-CASE-FOLDER-NEVER-PUBLIC",
        )
        title = "Public multi-asset case title"
        note = "One concise public note for the case."
        public_case = self.create_public_case(
            patient=patient,
            reference_visit=reference_visit,
            title=title,
            note=note,
        )
        rows = []
        for index in range(3):
            rows.append(
                self.create_media(
                    patient=patient,
                    visit=before_visit,
                    folder=folder,
                    public_case=public_case,
                    public_case_role=RecordMedia.PublicCaseRole.BEFORE,
                    title=encode_public_case_title("before", title),
                    description=f"INTERNAL-BEFORE-DESCRIPTION-{index}",
                    file=self.synthetic_image_file(name=f"before-{index}.jpg"),
                )
            )
        for index in range(2):
            rows.append(
                self.create_media(
                    patient=patient,
                    visit=after_visit,
                    folder=folder,
                    public_case=public_case,
                    public_case_role=RecordMedia.PublicCaseRole.AFTER,
                    title=encode_public_case_title("after", title),
                    description=f"INTERNAL-AFTER-DESCRIPTION-{index}",
                    file=self.synthetic_image_file(name=f"after-{index}.jpg"),
                )
            )
        videos = []
        for index in range(2):
            videos.append(
                self.create_media(
                    patient=patient,
                    visit=video_visit,
                    folder=folder,
                    public_case=public_case,
                    public_case_role=RecordMedia.PublicCaseRole.VIDEO,
                    media_type=RecordMedia.MediaType.SHORT_VIDEO,
                    title=encode_public_case_title("video", title),
                    description=f"INTERNAL-VIDEO-DESCRIPTION-{index}",
                    file=self.synthetic_video_file(name=f"video-{index}.mp4"),
                )
            )
        cover = self.create_media(
            patient=patient,
            visit=video_visit,
            folder=folder,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.VIDEO_COVER,
            title=encode_public_case_title("video_cover", title),
            description="INTERNAL-COVER-DESCRIPTION",
            file=self.synthetic_image_file(name="cover.jpg"),
        )

        cases_response = self.client.get(reverse("public_cases_en"))
        cases_content = cases_response.content.decode()
        cover_url = reverse("public_case_media_en", kwargs={"public_id": cover.public_id})

        self.assertContains(
            cases_response,
            'class="public-case-card public-case-album-card"',
            count=1,
        )
        self.assertContains(cases_response, title, count=1)
        self.assertContains(cases_response, note, count=1)
        self.assertNotIn("public-case-video-grid", cases_content)
        self.assertNotIn("public-case-image-grid", cases_content)
        self.assertEqual(cases_content.count("<video"), 2)
        self.assertEqual(cases_content.count(cover_url), 1)
        for media in rows + videos:
            protected_url = reverse(
                "public_case_media_en",
                kwargs={"public_id": media.public_id},
            )
            self.assertIn(protected_url, cases_content)
        self.assertContains(cases_response, "data-case-carousel", count=1)
        self.assertContains(cases_response, "data-case-slide\n", count=7)
        self.assertContains(cases_response, "data-case-controls", count=1)
        self.assertContains(cases_response, "data-case-lightbox", count=1)
        self.assertContains(cases_response, 'data-slide-label="Video 1 of 2"', count=1)
        self.assertContains(cases_response, 'data-slide-label="Video 2 of 2"', count=1)
        self.assertContains(cases_response, 'data-slide-label="Before 1 of 3"', count=1)
        self.assertContains(cases_response, 'data-slide-label="After 1 of 2"', count=1)
        self.assertNotContains(cases_response, "public-case-view-action")

        detail_response = self.client.get(
            reverse("public_case_detail_en", kwargs={"case_id": public_case.pk})
        )
        detail_content = detail_response.content.decode()
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, title, count=1)
        self.assertContains(detail_response, note, count=1)
        self.assertContains(detail_response, ">Videos</h2>", count=1)
        self.assertContains(detail_response, ">Before</h2>", count=1)
        self.assertContains(detail_response, ">After</h2>", count=1)
        self.assertEqual(detail_content.count("<video"), 2)
        for media in rows + videos:
            protected_url = reverse(
                "public_case_media_en",
                kwargs={"public_id": media.public_id},
            )
            self.assertEqual(detail_content.count(protected_url), 2 if media in rows else 1)
        self.assertEqual(detail_content.count(f'poster="{cover_url}"'), 1)
        self.assertNotIn(f'src="{cover_url}"', detail_content)
        self.assertNotIn("[[public-case:", cases_content)
        self.assertNotIn(folder.name, cases_content)
        self.assertNotIn(patient.full_name, cases_content)
        self.assertNotIn(patient.phone_raw, cases_content)
        self.assertNotIn(reference_visit.visit_reason, cases_content)
        self.assertNotIn("INTERNAL-BEFORE-DESCRIPTION", cases_content)
        self.assertNotIn("INTERNAL-AFTER-DESCRIPTION", cases_content)
        self.assertNotIn("INTERNAL-VIDEO-DESCRIPTION", cases_content)
        self.assertNotIn("INTERNAL-COVER-DESCRIPTION", cases_content)
        self.assertNotIn('href="/media/', cases_content)

        home_response = self.client.get(reverse("home_en"))
        home_content = home_response.content.decode()
        video_urls = [
            reverse("public_case_media_en", kwargs={"public_id": video.public_id})
            for video in videos
        ]
        self.assertContains(home_response, title, count=1)
        self.assertContains(home_response, note, count=1)
        self.assertEqual(sum(home_content.count(url) for url in video_urls), 0)
        self.assertEqual(home_content.count(cover_url), 1)
        self.assertContains(
            home_response,
            reverse("public_case_detail_en", kwargs={"case_id": public_case.pk}),
        )
        self.assertNotIn(folder.name, home_content)
        for image in rows:
            image_url = reverse(
                "public_case_media_en",
                kwargs={"public_id": image.public_id},
            )
            self.assertNotIn(image_url, home_content)

    def test_public_group_updates_immediately_when_items_are_unpublished(self):
        patient = self.create_patient(
            full_name="Synthetic Unpublish Hidden Patient",
            phone_raw="0790000555",
            phone_e164="+962790000555",
        )
        visit = self.create_visit(patient=patient)
        before = self.create_media(patient=patient, visit=visit, title="Before")
        after = self.create_media(patient=patient, visit=visit, title="After")
        video = self.create_media(
            patient=patient,
            visit=visit,
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            title="",
        )
        before_url = reverse("public_case_media_en", kwargs={"public_id": before.public_id})
        after_url = reverse("public_case_media_en", kwargs={"public_id": after.public_id})
        video_url = reverse("public_case_media_en", kwargs={"public_id": video.public_id})

        detail_url = reverse(
            "public_case_detail_en",
            kwargs={"case_id": before.public_case_id},
        )
        initial = self.client.get(detail_url)
        for url in (before_url, after_url, video_url):
            self.assertContains(initial, url)

        after.is_active = False
        after.save(update_fields=["is_active"])
        after_removed = self.client.get(detail_url)
        self.assertNotContains(after_removed, after_url)
        self.assertContains(after_removed, before_url)
        self.assertContains(after_removed, video_url)

        before.visibility = RecordMedia.Visibility.PRIVATE_ONLY
        before.save(update_fields=["visibility"])
        before_removed = self.client.get(detail_url)
        self.assertNotContains(before_removed, before_url)
        self.assertNotContains(before_removed, after_url)
        self.assertContains(before_removed, video_url)

        self.force_unconsented_public_case(video)
        consent_removed = self.client.get(detail_url)
        self.assertEqual(consent_removed.status_code, 404)

    def test_unpublished_and_unconsented_cases_are_absent_from_public_pages(self):
        unpublished_case = self.create_public_case(
            title="UNPUBLISHED-CASE-MUST-STAY-HIDDEN",
            is_published=False,
        )
        unpublished_media = self.create_media(
            patient=unpublished_case.patient,
            public_case=unpublished_case,
            title="UNPUBLISHED-MEDIA-MUST-STAY-HIDDEN",
        )
        unconsented_case = self.create_public_case(
            title="UNCONSENTED-CASE-MUST-STAY-HIDDEN",
            consent_confirmed=False,
        )
        unconsented_media = self.create_media(
            patient=unconsented_case.patient,
            public_case=unconsented_case,
            title="UNCONSENTED-CASE-MEDIA-MUST-STAY-HIDDEN",
        )

        for route_name in ("public_cases_en", "home_en"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertNotContains(response, unpublished_case.title)
                self.assertNotContains(response, unconsented_case.title)
                self.assertNotContains(
                    response,
                    reverse(
                        "public_case_media_en",
                        kwargs={"public_id": unpublished_media.public_id},
                    ),
                )
                self.assertNotContains(
                    response,
                    reverse(
                        "public_case_media_en",
                        kwargs={"public_id": unconsented_media.public_id},
                    ),
                )

    def test_home_uses_one_teaser_asset_with_before_after_primary_priority(self):
        public_case = self.create_public_case(
            title="Home explicit public case teaser",
            note="Concise home teaser note.",
        )
        primary = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.PRIMARY,
            title="INTERNAL-HOME-PRIMARY-TITLE",
            file=self.synthetic_image_file(name="synthetic-primary.jpg"),
        )
        before = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
            title="INTERNAL-HOME-BEFORE-TITLE",
            file=self.synthetic_image_file(name="synthetic-before.jpg"),
        )
        after = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.AFTER,
            title="INTERNAL-HOME-AFTER-TITLE",
            file=self.synthetic_image_file(name="synthetic-after.jpg"),
        )
        self.create_media(
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Home patient-visible teaser must stay hidden",
        )

        response = self.client.get(reverse("home_en"))
        content = response.content.decode()
        primary_url = reverse(
            "public_case_media_en",
            kwargs={"public_id": primary.public_id},
        )
        before_url = reverse(
            "public_case_media_en",
            kwargs={"public_id": before.public_id},
        )
        after_url = reverse(
            "public_case_media_en",
            kwargs={"public_id": after.public_id},
        )

        self.assertContains(response, public_case.title, count=1)
        self.assertContains(response, public_case.note, count=1)
        self.assertContains(response, 'class="case-card"', count=1)
        self.assertContains(
            response,
            reverse("public_case_detail_en", kwargs={"case_id": public_case.pk}),
        )
        self.assertEqual(content.count(before_url), 1)
        self.assertNotIn(after_url, content)
        self.assertNotIn(primary_url, content)
        self.assertNotIn("INTERNAL-HOME-PRIMARY-TITLE", content)
        self.assertNotIn("INTERNAL-HOME-BEFORE-TITLE", content)
        self.assertNotIn("INTERNAL-HOME-AFTER-TITLE", content)
        self.assertNotContains(response, "Home patient-visible teaser must stay hidden")
        self.assertNotContains(response, primary.file.name)
        self.assertNotContains(response, before.file.name)
        self.assertNotContains(response, after.file.name)
        self.assertNotContains(response, "synthetic-primary.jpg")
        self.assertNotContains(response, "synthetic-before.jpg")
        self.assertNotContains(response, "synthetic-after.jpg")
        self.assertNotContains(response, str(settings.PRIVATE_MEDIA_ROOT))


    def test_listing_cover_priority_and_detail_keep_one_public_case_album(self):
        public_case = self.create_public_case(
            title="Synthetic representative cover priority",
            note="One concise album note.",
        )
        primary = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.PRIMARY,
        )
        after = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.AFTER,
        )
        before = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
        )
        video = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.VIDEO,
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
        )
        cover = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.VIDEO_COVER,
        )
        urls = {
            media.pk: reverse(
                "public_case_media_en",
                kwargs={"public_id": media.public_id},
            )
            for media in (primary, after, before, video, cover)
        }

        listing = self.client.get(reverse("public_cases_en"))
        listing_content = listing.content.decode()
        self.assertContains(listing, 'class="public-case-card public-case-album-card"', count=1)
        self.assertEqual(listing_content.count(urls[cover.pk]), 1)
        for media in (primary, after, before, video):
            self.assertIn(urls[media.pk], listing_content)
        self.assertEqual(listing_content.count("data-case-slide\n"), 4)
        self.assertNotIn(f'data-media-public-id="{cover.public_id}"', listing_content)
        self.assertIn(f'poster="{urls[cover.pk]}"', listing_content)

        detail = self.client.get(
            reverse("public_case_detail_en", kwargs={"case_id": public_case.pk})
        )
        detail_content = detail.content.decode()
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, public_case.title, count=1)
        self.assertContains(detail, public_case.note, count=1)
        self.assertEqual(detail_content.count(f'poster="{urls[cover.pk]}"'), 1)
        self.assertNotIn(f'src="{urls[cover.pk]}"', detail_content)
        self.assertEqual(detail_content.count(urls[video.pk]), 1)
        for media in (primary, after, before):
            self.assertEqual(detail_content.count(urls[media.pk]), 2)

    def test_detail_hides_unpublished_unconsented_and_trashed_assets(self):
        visible_case = self.create_public_case(title="Visible album with one retained asset")
        visible = self.create_media(
            patient=visible_case.patient,
            public_case=visible_case,
            public_case_role=RecordMedia.PublicCaseRole.AFTER,
        )
        trashed = self.create_media(
            patient=visible_case.patient,
            public_case=visible_case,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
        )
        RecordMedia.objects.filter(pk=trashed.pk).update(
            trashed_at=timezone.now(),
            is_active=False,
        )

        listing = self.client.get(reverse("public_cases_en"))
        self.assertContains(
            listing,
            reverse("public_case_media_en", kwargs={"public_id": visible.public_id}),
        )
        self.assertNotContains(
            listing,
            reverse("public_case_media_en", kwargs={"public_id": trashed.public_id}),
        )
        self.assertContains(listing, "data-case-slide\n", count=1)
        self.assertNotContains(listing, "data-case-controls")

        detail = self.client.get(
            reverse("public_case_detail_en", kwargs={"case_id": visible_case.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(
            detail,
            reverse("public_case_media_en", kwargs={"public_id": visible.public_id}),
        )
        self.assertNotContains(
            detail,
            reverse("public_case_media_en", kwargs={"public_id": trashed.public_id}),
        )
        self.assertEqual(
            self.client.get(
                reverse("public_case_media_en", kwargs={"public_id": trashed.public_id})
            ).status_code,
            404,
        )

        unpublished_case = self.create_public_case(is_published=False)
        self.create_media(
            patient=unpublished_case.patient,
            public_case=unpublished_case,
        )
        unconsented_case = self.create_public_case(consent_confirmed=False)
        self.create_media(
            patient=unconsented_case.patient,
            public_case=unconsented_case,
        )
        for public_case in (unpublished_case, unconsented_case):
            with self.subTest(case_id=public_case.pk):
                self.assertEqual(
                    self.client.get(
                        reverse(
                            "public_case_detail_en",
                            kwargs={"case_id": public_case.pk},
                        )
                    ).status_code,
                    404,
                )


class PublicCaseMediaRouteTests(PublicCasesTestDataMixin, TestCase):
    def test_approved_public_case_media_returns_file_response(self):
        patient = self.create_patient(full_name="Synthetic Header Hidden Patient")
        media = self.create_media(
            patient=patient,
            file=self.synthetic_image_file(name="synthetic-public-case.jpg", content=b"approved-public-bytes"),
        )

        response = self.client.get(reverse("public_case_media", kwargs={"public_id": media.public_id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn(f"public-case-{media.public_id}.jpg", response.get("Content-Disposition", ""))
        self.assertNotIn("synthetic-public-case.jpg", response.get("Content-Disposition", ""))
        headers = "\n".join(f"{key}: {value}" for key, value in response.headers.items())
        self.assertNotIn(str(settings.PRIVATE_MEDIA_ROOT), headers)
        self.assertNotIn(media.file.name, headers)
        self.assertNotIn(patient.full_name, headers)
        self.assertNotIn(patient.phone_raw, headers)
        self.assertEqual(b"".join(response.streaming_content), b"approved-public-bytes")
        response.close()
        with self.assertRaises(ValueError):
            media.file.url

    def test_unpublishing_case_immediately_denies_previously_public_media(self):
        public_case = self.create_public_case(title="Temporary public case")
        media = self.create_media(
            patient=public_case.patient,
            public_case=public_case,
            title="INTERNAL-TEMPORARY-PUBLIC-MEDIA",
        )
        media_url = reverse("public_case_media", kwargs={"public_id": media.public_id})

        published_response = self.client.get(media_url)
        self.assertEqual(published_response.status_code, 200)
        published_response.close()

        public_case.is_published = False
        public_case.save(update_fields=["is_published"])

        denied_response = self.client.get(media_url)
        self.assertEqual(denied_response.status_code, 404)

    def test_non_public_or_inactive_media_return_404(self):
        blocked_media = [
            self.create_media(
                visibility=RecordMedia.Visibility.PRIVATE_ONLY,
                title="Private-only public route block",
            ),
            self.create_media(
                visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
                title="Patient-visible public route block",
            ),
            self.create_media(
                is_active=False,
                title="Inactive public route block",
            ),
        ]

        for media in blocked_media:
            with self.subTest(media=media.title):
                response = self.client.get(reverse("public_case_media", kwargs={"public_id": media.public_id}))

                self.assertEqual(response.status_code, 404)

    def test_unconsented_public_case_media_returns_404(self):
        media = self.create_media(title="Unconsented public media route block")
        self.force_unconsented_public_case(media)

        response = self.client.get(reverse("public_case_media", kwargs={"public_id": media.public_id}))

        self.assertEqual(response.status_code, 404)

    def test_missing_media_and_missing_files_return_404(self):
        missing_media_response = self.client.get(
            reverse("public_case_media", kwargs={"public_id": uuid.uuid4()})
        )
        missing_file = self.create_media(title="Missing file field public route block")
        RecordMedia.objects.filter(pk=missing_file.pk).update(file="")
        missing_file_response = self.client.get(
            reverse("public_case_media", kwargs={"public_id": missing_file.public_id})
        )
        missing_storage_file = self.create_media(title="Missing storage file public route block")
        missing_storage_file.file.storage.delete(missing_storage_file.file.name)
        missing_storage_file_response = self.client.get(
            reverse("public_case_media", kwargs={"public_id": missing_storage_file.public_id})
        )

        self.assertEqual(missing_media_response.status_code, 404)
        self.assertEqual(missing_file_response.status_code, 404)
        self.assertEqual(missing_storage_file_response.status_code, 404)


class PublicCaseResponsiveSourceContractTests(SimpleTestCase):
    def test_cases_template_renders_album_cards_without_full_galleries(self):
        template = (settings.BASE_DIR / "templates" / "core" / "cases.html").read_text(
            encoding="utf-8"
        )

        self.assertEqual(
            template.count('<article class="public-case-card public-case-album-card"'),
            1,
        )
        self.assertIn("case.carousel_items", template)
        self.assertIn("data-case-carousel", template)
        self.assertIn("data-case-slide", template)
        self.assertIn("data-slide-kind", template)
        self.assertIn("data-case-current-label", template)
        self.assertIn("data-case-counter", template)
        self.assertIn("data-case-prev", template)
        self.assertIn("data-case-next", template)
        self.assertIn("data-case-expand", template)
        self.assertIn("data-media-public-id", template)
        self.assertIn("data-media-type", template)
        self.assertIn("data-media-role", template)
        self.assertIn("data-media-url", template)
        self.assertIn("data-slide-label", template)
        self.assertIn("data-case-note-text", template)
        self.assertIn("slide.kind == 'note'", template)
        self.assertIn('preload="none"', template)
        self.assertIn("muted playsinline controls", template)
        self.assertNotIn("autoplay", template)
        self.assertNotIn("media.title", template)
        self.assertNotIn("media.description", template)
        self.assertNotIn("media.file", template)
        self.assertIn("case.detail_url", template)
        self.assertIn("<noscript>", template)
        self.assertNotIn("public-case-view-action", template)
        self.assertNotIn('class="btn btn-secondary', template)
        self.assertNotIn("case.before_items", template)
        self.assertNotIn("case.after_items", template)
        self.assertNotIn("case.video_items", template)

        self.assertEqual(template.count("<dialog"), 1)
        self.assertIn("data-case-lightbox", template)
        self.assertIn("data-lightbox-title", template)
        self.assertIn("data-lightbox-label", template)
        self.assertIn("data-lightbox-counter", template)
        self.assertIn("data-lightbox-media", template)
        self.assertIn("data-lightbox-prev", template)
        self.assertIn("data-lightbox-next", template)
        self.assertIn("data-lightbox-close", template)

        detail_template = (
            settings.BASE_DIR / "templates" / "core" / "case_detail.html"
        ).read_text(encoding="utf-8")
        self.assertIn("public_case.before_items", detail_template)
        self.assertIn("public_case.after_items", detail_template)
        self.assertIn("public_case.video_items", detail_template)
        self.assertIn("public_case.detail_note", detail_template)
        self.assertIn("Case Notes", detail_template)
        self.assertIn('poster="{{ video.poster_url }}"', detail_template)
        self.assertNotIn("public_case.video_cover.url", detail_template)

    def test_home_template_uses_only_the_selected_teaser_and_links_to_cases(self):
        template = (settings.BASE_DIR / "templates" / "core" / "home.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("case.teaser.media_type", template)
        self.assertIn("case.teaser.url", template)
        self.assertNotIn("case.before_items", template)
        self.assertNotIn("case.after_items", template)
        self.assertNotIn("case.video_items", template)
        self.assertNotIn("case.primary.url", template)
        self.assertIn('href="{{ cases_url }}"', template)

    def test_case_video_css_is_intrinsic_bounded_and_logical(self):
        css = (settings.BASE_DIR / "static" / "css" / "public-closeout.css").read_text(
            encoding="utf-8"
        )
        video_rule = re.search(r"\.public-case-video-frame video\s*\{(?P<body>[^}]*)\}", css)

        self.assertIsNotNone(video_rule)
        video_body = video_rule.group("body")
        for declaration in (
            "display: block",
            "inline-size: auto",
            "max-inline-size: 100%",
            "block-size: auto",
            "object-fit: contain",
            "margin-inline: auto",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, video_body)
        self.assertNotIn("width: 100%", video_body)
        self.assertNotIn("aspect-ratio", video_body)
        self.assertNotIn("object-fit: cover", video_body)
        self.assertIn("min(60svh, 34rem)", css)
        self.assertIn("min(68svh, 42rem)", css)
        self.assertIn("padding-inline:", css)
        self.assertIn("padding-block:", css)
        self.assertNotRegex(css, r"padding-(?:left|right):")

    def test_album_listing_and_detail_have_phone_tablet_desktop_contracts(self):
        css = (settings.BASE_DIR / "static" / "css" / "public-closeout.css").read_text(
            encoding="utf-8"
        )
        base_css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(
            encoding="utf-8"
        )

        base_grid = re.search(r"\.public-case-album-grid\s*\{(?P<body>[^}]*)\}", css)
        card_rule = re.search(r"\.public-case-album-card\s*\{(?P<body>[^}]*)\}", css)
        stage_rule = re.search(r"\.public-case-carousel-stage\s*\{(?P<body>[^}]*)\}", css)
        slide_rule = re.search(r"\.public-case-carousel-slide\s*\{(?P<body>[^}]*)\}", css)
        media_rule = re.search(
            r"\.public-case-carousel-slide > img,\s*"
            r"\.public-case-carousel-slide > video\s*\{(?P<body>[^}]*)\}",
            css,
        )
        lightbox_viewport_rule = re.search(
            r"\.public-case-lightbox-media\s*\{(?P<body>[^}]*)\}",
            css,
        )
        lightbox_media_rule = re.search(
            r"\.public-case-lightbox-media > img,\s*"
            r"\.public-case-lightbox-media > video\s*\{(?P<body>[^}]*)\}",
            css,
        )

        self.assertIsNotNone(base_grid)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", base_grid.group("body"))
        self.assertIn("max-inline-size: 80rem", base_grid.group("body"))
        self.assertIn("margin-inline: auto", base_grid.group("body"))
        self.assertIn("align-items: start", base_grid.group("body"))
        self.assertRegex(
            css,
            r"(?s)@media \(min-width: 48rem\).*?\.public-case-album-grid\s*\{[^}]*repeat\(2, minmax\(0, 1fr\)\)",
        )
        self.assertRegex(
            css,
            r"(?s)@media \(min-width: 64rem\).*?\.public-case-album-grid\s*\{[^}]*repeat\(3, minmax\(0, 1fr\)\)",
        )
        self.assertIsNotNone(card_rule)
        for declaration in ("min-height: 0", "height: auto", "align-self: start"):
            self.assertIn(declaration, card_rule.group("body"))
        self.assertIsNotNone(stage_rule)
        stage_body = stage_rule.group("body")
        self.assertIn("inline-size: 100%", stage_body)
        self.assertIn("aspect-ratio: 4 / 3", stage_body)
        self.assertIn("overflow: hidden", stage_body)
        self.assertIsNotNone(slide_rule)
        for declaration in (
            "inline-size: 100%",
            "block-size: 100%",
            "min-width: 0",
            "min-height: 0",
            "box-sizing: border-box",
        ):
            self.assertIn(declaration, slide_rule.group("body"))
        self.assertNotIn("transform:", slide_rule.group("body"))
        self.assertIsNotNone(media_rule)
        media_body = media_rule.group("body")
        for declaration in (
            "display: block",
            "inline-size: 100%",
            "block-size: 100%",
            "min-inline-size: 0",
            "min-block-size: 0",
            "margin: auto",
            "object-fit: contain",
            "object-position: center",
        ):
            with self.subTest(declaration=declaration):
                self.assertIn(declaration, media_body)
        self.assertNotIn("inline-size: auto", media_body)
        self.assertNotIn("block-size: auto", media_body)
        self.assertNotIn("object-fit: cover", media_body)

        self.assertIsNotNone(lightbox_viewport_rule)
        lightbox_viewport_body = lightbox_viewport_rule.group("body")
        for declaration in (
            "inline-size: 100%",
            "min-width: 0",
            "min-height: 12rem",
            "height: min(66svh, 46rem)",
            "box-sizing: border-box",
            "overflow: hidden",
        ):
            self.assertIn(declaration, lightbox_viewport_body)
        self.assertIsNotNone(lightbox_media_rule)
        lightbox_media_body = lightbox_media_rule.group("body")
        for declaration in (
            "inline-size: 100%",
            "block-size: 100%",
            "min-inline-size: 0",
            "min-block-size: 0",
            "object-fit: contain",
            "object-position: center",
        ):
            self.assertIn(declaration, lightbox_media_body)
        self.assertNotIn("width: auto", lightbox_media_body)
        self.assertNotIn("height: auto", lightbox_media_body)
        self.assertNotIn("object-fit: cover", lightbox_media_body)
        self.assertIn(".public-case-carousel-note-slide", css)
        self.assertIn(".public-case-lightbox-note", css)
        for rule in re.finditer(
            r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}",
            f"{base_css}\n{css}",
        ):
            selectors = rule.group("selectors")
            if not (
                (".public-case-carousel" in selectors or ".public-case-lightbox-media" in selectors)
                and ("img" in selectors or "video" in selectors)
            ):
                continue
            with self.subTest(selectors=selectors.strip()):
                self.assertNotIn("object-fit: cover", rule.group("body"))
        self.assertIn("padding: clamp(", css)
        self.assertIn("-webkit-line-clamp: 2", css)
        self.assertNotIn(".public-case-view-action", css)
        self.assertIn(".public-case-detail-galleries", css)
        self.assertNotRegex(css, r"padding-(?:left|right):")

    def test_case_carousel_and_lightbox_javascript_contracts(self):
        javascript = (
            settings.BASE_DIR / "static" / "js" / "public-closeout.js"
        ).read_text(encoding="utf-8")
        template = (settings.BASE_DIR / "templates" / "core" / "cases.html").read_text(
            encoding="utf-8"
        )

        for contract in (
            "enforceSilentPlayback",
            "pauseCaseVideos",
            "showCaseSlide",
            "caseNavigationOffsetForKey",
            "openCaseLightbox",
            "renderLightboxSlide",
            'slide.dataset.slideKind === "note"',
            'slide.querySelector("[data-case-note-text]")',
            'noteCard.className = "public-case-lightbox-note"',
            "closeCaseLightbox",
            'querySelectorAll("[data-case-album]")',
            "caseState.index",
            "video.pause()",
            "video.defaultMuted = true",
            "video.muted = true",
            "initializePublicCloseout",
            "initializeCaseCarousels",
            'document.readyState === "loading"',
            'document.addEventListener("DOMContentLoaded"',
            'typeof lightbox.showModal === "function"',
            'carousel.dataset.caseCarouselReady = "true"',
            "window.location.assign(caseState.detailUrl)",
            "lightbox.showModal()",
            "lightbox.close()",
            "lightboxMedia.replaceChildren()",
            'event.key === "Escape"',
            '"ArrowLeft"',
            '"ArrowRight"',
            'document.documentElement.dir === "rtl"',
            "opener.focus({ preventScroll: true })",
            "event.preventDefault()",
            "event.stopPropagation()",
            'target.closest(interactiveCaseSelector)',
            'querySelectorAll("[data-review-carousel]")',
            "addMediaQueryChangeListener",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, javascript)
        self.assertNotIn(".play()", javascript)
        self.assertNotIn("detailNote", javascript)
        self.assertIn('data-case-detail-url="{{ case.detail_url }}"', template)

    def test_case_carousel_and_lightbox_runtime_behavior(self):
        runtime_test = (
            settings.BASE_DIR
            / "apps"
            / "core"
            / "js_tests"
            / "public_case_carousel_runtime_test.js"
        )
        public_closeout_script = (
            settings.BASE_DIR / "static" / "js" / "public-closeout.js"
        )

        result = subprocess.run(
            ["node", str(runtime_test), str(public_closeout_script)],
            cwd=settings.BASE_DIR,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=(
                "Public case carousel behavior failed:\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            ),
        )
        self.assertIn("public case carousel runtime behavior passed", result.stdout)


class PublicCasesRegressionBoundaryTests(PublicCasesTestDataMixin, TestCase):
    def test_internal_folder_metadata_never_appears_in_patient_portal(self):
        user = get_user_model().objects.create_user(
            username="+962790000332",
            password="synthetic-test-password",
        )
        patient = self.create_patient(
            user=user,
            full_name="Synthetic Portal Folder Patient",
            phone_raw="0790000332",
            phone_e164="+962790000332",
        )
        folder = RecordMediaFolder.objects.create(
            patient=patient,
            name="PORTAL-MUST-NEVER-SEE-THIS-FOLDER",
        )
        visible_media = self.create_media(
            patient=patient,
            folder=folder,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Patient-visible media with internal folder",
        )
        self.create_media(
            patient=patient,
            folder=folder,
            title="Approved public case remains outside portal media",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patient_portal_medical_records_en"))

        self.assertContains(response, visible_media.title)
        self.assertNotContains(response, folder.name)
        self.assertNotContains(response, "Approved public case remains outside portal media")

    def test_patient_portal_media_route_still_only_serves_linked_patient_visible_media(self):
        user = get_user_model().objects.create_user(
            username="+962790000333",
            email="synthetic-public-case-portal@example.test",
            password="synthetic-test-password",
        )
        patient = self.create_patient(user=user, phone_raw="0790000333", phone_e164="+962790000333")
        visible_media = self.create_media(
            patient=patient,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Patient-visible media remains portal-only",
            file=self.synthetic_image_file(name="synthetic-public-case.jpg", content=b"patient-visible-bytes"),
        )
        public_case_media = self.create_media(
            patient=patient,
            title="Public case media is not patient portal media",
        )
        private_media = self.create_media(
            patient=patient,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
            title="Private media is not patient portal media",
        )
        self.client.force_login(user)

        visible_response = self.client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": visible_media.public_id},
            )
        )
        public_case_response = self.client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": public_case_media.public_id},
            )
        )
        private_response = self.client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": private_media.public_id},
            )
        )

        self.assertEqual(visible_response.status_code, 200)
        self.assertEqual(b"".join(visible_response.streaming_content), b"patient-visible-bytes")
        visible_response.close()
        self.assertEqual(public_case_response.status_code, 404)
        self.assertEqual(private_response.status_code, 404)

    def test_staff_private_media_route_remains_staff_only(self):
        media = self.create_media(title="Staff route public case access control")
        normal_user = get_user_model().objects.create_user(
            username="synthetic-normal-public-case-user",
            password="synthetic-test-password",
        )

        anonymous_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )
        self.client.force_login(normal_user)
        normal_user_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(anonymous_response.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", anonymous_response["Location"])
        self.assertEqual(normal_user_response.status_code, 403)

    def test_unlisted_and_prohibited_routes_remain_absent(self):
        blocked_paths = [
            "/uploads/",
            "/portal/uploads/",
            "/whatsapp/webhook/",
            "/api/whatsapp/",
            "/whatsapp/api/",
            "/records/",
            "/medical-records/",
            "/payments/",
            "/portal/payments/",
        ]

        for path in blocked_paths:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 404)


class PublicPageSmokeTests(TestCase):
    def test_arabic_public_pages_return_200(self):
        route_names = [
            "home",
            "doctor",
            "services",
            "public_cases",
            "contact",
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
        ]

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)

    def test_english_public_pages_return_200(self):
        route_names = [
            "home_en",
            "doctor_en",
            "services_en",
            "public_cases_en",
            "contact_en",
        ]

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)


class PublicPageContentTests(TestCase):
    def test_arabic_clinic_name_appears_on_arabic_home(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "عيادة الدكتور خالد بدران")

    def test_english_clinic_name_appears_on_english_home(self):
        response = self.client.get(reverse("home_en"))

        self.assertContains(response, "Dr. Khaled Badran Clinic")

    def test_doctor_name_appears_on_doctor_page(self):
        response = self.client.get(reverse("doctor"))

        self.assertContains(response, "د. خالد حسان بدران")

    def test_services_page_includes_fallback_service(self):
        response = self.client.get(reverse("services"))

        self.assertContains(response, "كشف جديد")

    def test_legal_pages_include_legal_review_or_emergency_disclaimer(self):
        route_names = [
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
        ]

        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertContains(response, "مراجعة قانونية")

    def test_booking_cta_points_to_public_booking_flow(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'href="/book/"')
        self.assertNotContains(response, "<form")

    def test_public_pages_do_not_create_appointments(self):
        route_names = [
            "home",
            "doctor",
            "services",
            "public_cases",
            "contact",
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
            "home_en",
            "doctor_en",
            "services_en",
            "public_cases_en",
            "contact_en",
        ]

        for route_name in route_names:
            self.client.get(reverse(route_name))

        self.assertEqual(Appointment.objects.count(), 0)

    def test_robots_and_sitemap_routes_render(self):
        robots_response = self.client.get(reverse("robots_txt"))
        sitemap_response = self.client.get(reverse("sitemap_xml"))

        self.assertContains(robots_response, "Sitemap:")
        self.assertContains(sitemap_response, "<urlset", status_code=200)


class PublicUiFoundationTests(TestCase):
    public_stylesheet_href = f'href="{settings.STATIC_URL}css/public.css"'
    service_dictionary_leak_markers = (
        "('name',",
        "('name_ar',",
        "('name_en',",
        "('duration_minutes',",
        "('instructions',",
        "('price', None)",
        "('visible_price', None)",
    )

    def create_public_visit_type(self, *, price=None, show_price=False):
        return VisitType.objects.create(
            name_ar="استشارة اختبار عامة",
            name_en="Synthetic public consultation",
            duration_minutes=30,
            instructions_ar="تعليمات عامة للاختبار فقط.",
            instructions_en="Synthetic public instructions only.",
            price=price,
            show_price_to_patient=show_price,
            is_active=True,
            display_order=0,
        )

    def assert_no_service_dictionary_leak(self, response):
        rendered_html = html_lib.unescape(response.content.decode())
        for marker in self.service_dictionary_leak_markers:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, rendered_html)
        self.assertNotIn("duration_minutes", rendered_html)

    def assert_public_shell(self, response, *, has_mobile_booking_cta):
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("public-shell", html)
        self.assertIn(self.public_stylesheet_href, html)
        if has_mobile_booking_cta:
            self.assertIn("data-mobile-booking-cta", html)
        else:
            self.assertNotIn("data-mobile-booking-cta", html)

    def assert_non_public_shell(self, response):
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("public-shell", html)
        self.assertNotIn(self.public_stylesheet_href, html)
        self.assertNotIn("data-mobile-booking-cta", html)

    def test_public_language_direction_is_natural_for_arabic_and_english(self):
        arabic = self.client.get(reverse("home"))
        english = self.client.get(reverse("home_en"))

        self.assertContains(arabic, '<html lang="ar" dir="rtl">')
        self.assertContains(english, '<html lang="en" dir="ltr">')

    def test_arabic_services_render_explicit_visit_type_fields_without_dictionary_leak(self):
        self.create_public_visit_type()

        response = self.client.get(reverse("services"))

        self.assertContains(response, "استشارة اختبار عامة")
        self.assertContains(response, "30 دقيقة")
        self.assertContains(response, "تعليمات عامة للاختبار فقط.")
        self.assertNotContains(response, "Synthetic public consultation")
        self.assertNotContains(response, "السعر:")
        self.assert_no_service_dictionary_leak(response)

    def test_english_services_render_explicit_visit_type_fields_without_dictionary_leak(self):
        self.create_public_visit_type()

        response = self.client.get(reverse("services_en"))

        self.assertContains(response, "Synthetic public consultation")
        self.assertContains(response, "30 minutes")
        self.assertContains(response, "Synthetic public instructions only.")
        self.assertNotContains(response, "استشارة اختبار عامة")
        self.assertNotContains(response, "Price:")
        self.assert_no_service_dictionary_leak(response)

    def test_home_omits_visit_type_services_while_services_routes_remain_available(self):
        self.create_public_visit_type()

        arabic_home = self.client.get(reverse("home"))
        english_home = self.client.get(reverse("home_en"))
        arabic_services = self.client.get(reverse("services"))
        english_services = self.client.get(reverse("services_en"))

        self.assertNotContains(arabic_home, "استشارة اختبار عامة")
        self.assertNotContains(english_home, "Synthetic public consultation")
        self.assertNotContains(arabic_home, 'class="section home-services"')
        self.assertNotContains(english_home, 'class="section home-services"')
        self.assertContains(arabic_services, "استشارة اختبار عامة")
        self.assertContains(english_services, "Synthetic public consultation")
        for response in [arabic_home, english_home, arabic_services, english_services]:
            self.assert_no_service_dictionary_leak(response)

    def test_visible_visit_type_price_is_rendered_only_when_intentionally_enabled(self):
        self.create_public_visit_type(price=Decimal("25.00"), show_price=True)

        arabic = self.client.get(reverse("services"))
        english = self.client.get(reverse("services_en"))

        self.assertContains(arabic, "السعر: 25.00")
        self.assertContains(english, "Price: 25.00")
        self.assert_no_service_dictionary_leak(arabic)
        self.assert_no_service_dictionary_leak(english)

    def test_service_cards_use_separate_explicit_template_contracts(self):
        visit_type_template = (
            settings.BASE_DIR / "templates" / "partials" / "service_card.html"
        ).read_text(encoding="utf-8")
        service_group_template = (
            settings.BASE_DIR / "templates" / "partials" / "service_group_card.html"
        ).read_text(encoding="utf-8")

        self.assertIn("visit_type.localized_name", visit_type_template)
        self.assertIn("visit_type.duration_minutes", visit_type_template)
        self.assertIn("service_group.bullet_items", service_group_template)
        self.assertNotIn("service.items", visit_type_template + service_group_template)

    def test_contact_location_is_canonical_and_legacy_contact_routes_redirect(self):
        self.assertEqual(reverse("contact"), "/contact-location/")
        self.assertEqual(reverse("contact_en"), "/en/contact-location/")

        arabic = self.client.get("/contact/", follow=False)
        english = self.client.get("/en/contact/", follow=False)

        self.assertEqual(arabic.status_code, 301)
        self.assertEqual(arabic["Location"], "/contact-location/")
        self.assertEqual(english.status_code, 301)
        self.assertEqual(english["Location"], "/en/contact-location/")

    def test_contact_location_uses_approved_map_phone_and_whatsapp_data(self):
        ClinicProfile.objects.create(
            official_name_ar="عيادة الدكتور خالد بدران",
            official_name_en="Dr. Khaled Badran Clinic",
            phone_raw="+962 7X XXX XXXX",
            address_ar="العنوان سيضاف بعد اعتماده",
            address_en="Address placeholder pending approval",
            is_active=True,
        )

        response = self.client.get(reverse("contact"))

        self.assertContains(response, "شارع رفيق العظم 13")
        self.assertContains(response, "31.970276,35.8934391")
        self.assertContains(response, "+962 7 8976 6332")
        self.assertContains(response, 'href="tel:+962789766332"')
        self.assertContains(response, 'href="https://wa.me/962789766332"')
        self.assertContains(response, "تواصل مع العيادة مباشرة عبر واتساب")
        self.assertNotContains(response, "+962 7X XXX XXXX")
        self.assertNotContains(response, "ساعات العمل")
        self.assertNotContains(response, "ساعات الدوام")

    def test_public_shell_has_accessible_mobile_drawer_and_language_switch_outside_it(self):
        response = self.client.get(reverse("services"))
        html = response.content.decode()

        self.assertIn('data-menu-toggle', html)
        self.assertIn('aria-controls="mobile-navigation"', html)
        self.assertIn('id="mobile-navigation"', html)
        self.assertIn('class="is-active" aria-current="page">الخدمات</a>', html)
        self.assertIn('data-mobile-booking-cta', html)

        language_switch_position = html.index('class="mobile-language-switch"')
        drawer_start = html.index('id="mobile-navigation"')
        drawer_end = html.index('</header>')
        drawer_html = html[drawer_start:drawer_end]
        self.assertLess(language_switch_position, drawer_start)
        self.assertNotIn('mobile-language-switch', drawer_html)

    def test_mobile_booking_cta_is_opted_in_only_on_approved_public_marketing_routes(self):
        approved_routes = [
            "home",
            "doctor",
            "services",
            "public_cases",
            "contact",
            "home_en",
            "doctor_en",
            "services_en",
            "public_cases_en",
            "contact_en",
        ]
        legal_routes = [
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
            "privacy_en",
            "terms_en",
            "medical_disclaimer_en",
            "whatsapp_policy_en",
        ]

        for route_name in approved_routes:
            with self.subTest(route=route_name):
                self.assert_public_shell(
                    self.client.get(reverse(route_name)),
                    has_mobile_booking_cta=True,
                )

        for route_name in legal_routes:
            with self.subTest(route=route_name):
                self.assert_public_shell(
                    self.client.get(reverse(route_name)),
                    has_mobile_booking_cta=False,
                )

    def test_booking_routes_use_public_shell_and_contact_footer_without_mobile_booking_cta(self):
        route_cases = [
            (
                "book",
                "contact",
                "login",
                "التواصل والموقع",
                "بوابة المريض",
            ),
            (
                "booking_visit_type",
                "contact",
                "login",
                "التواصل والموقع",
                "بوابة المريض",
            ),
            (
                "book_en",
                "contact_en",
                "login_en",
                "Contact &amp; Location",
                "Patient Portal",
            ),
            (
                "booking_visit_type_en",
                "contact_en",
                "login_en",
                "Contact &amp; Location",
                "Patient Portal",
            ),
        ]

        for route_name, contact_route, portal_route, contact_label, portal_label in route_cases:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assert_public_shell(response, has_mobile_booking_cta=False)
                self.assertContains(response, '<footer class="site-footer">')
                self.assertContains(
                    response,
                    (
                        f'<a class="btn btn-light" href="{reverse(contact_route)}">'
                        f"{contact_label}</a>"
                    ),
                    html=True,
                )
                self.assertContains(
                    response,
                    (
                        f'<a class="btn btn-outline-light" href="{reverse(portal_route)}">'
                        f"{portal_label}</a>"
                    ),
                    html=True,
                )

    def test_patient_auth_account_and_portal_routes_do_not_load_public_shell_or_mobile_booking_cta(self):
        anonymous_route_names = [
            "login",
            "patient_portal_login",
            "patient_portal_register",
            "login_en",
            "patient_portal_login_en",
            "patient_portal_register_en",
        ]

        for route_name in anonymous_route_names:
            with self.subTest(route=route_name):
                self.assert_non_public_shell(self.client.get(reverse(route_name)))

        user = get_user_model().objects.create_user(
            username="synthetic-batch-17-01-portal",
        )
        Patient.objects.create(
            user=user,
            full_name="Synthetic Batch 17 Portal Patient",
            phone_raw="synthetic-phone-1701",
            phone_e164="+000000001701",
        )
        self.client.force_login(user)

        for route_name in [
            "patient_portal_dashboard",
            "patient_portal_account",
            "patient_portal_medical_records",
            "patient_portal_dashboard_en",
            "patient_portal_account_en",
            "patient_portal_medical_records_en",
        ]:
            with self.subTest(route=route_name):
                self.assert_non_public_shell(self.client.get(reverse(route_name)))

    def test_staff_and_dashboard_routes_do_not_load_public_shell_or_mobile_booking_cta(self):
        staff_user = get_user_model().objects.create_user(
            username="synthetic-batch-17-01-staff",
            is_staff=True,
        )
        patient = Patient.objects.create(
            full_name="Synthetic Batch 17 Staff Record Patient",
            phone_raw="synthetic-phone-1702",
            phone_e164="+000000001702",
        )
        self.client.force_login(staff_user)

        route_requests = [
            ("staff_appointment_list", {}),
            ("dashboard_patient_list", {}),
            ("dashboard_patient_record_detail", {"patient_id": patient.id}),
        ]
        for route_name, kwargs in route_requests:
            with self.subTest(route=route_name):
                self.assert_non_public_shell(self.client.get(reverse(route_name, kwargs=kwargs)))

    @override_settings(DEBUG=False)
    def test_404_uses_public_branding_without_mobile_booking_cta(self):
        for path in ["/missing-public-shell-page/", "/en/missing-public-shell-page/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                html = response.content.decode()

                self.assertEqual(response.status_code, 404)
                self.assertIn("public-shell", html)
                self.assertIn(self.public_stylesheet_href, html)
                self.assertNotIn("data-mobile-booking-cta", html)

    def test_public_stylesheet_does_not_override_booking_or_staff_components(self):
        css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(encoding="utf-8")

        for selector in [
            ".booking-option",
            ".booking-summary",
            ".booking-form",
            ".slot-day",
            ".success-card",
            ".staff-filter-panel",
            ".staff-panel",
            ".staff-table-wrap",
            ".staff-messages",
        ]:
            with self.subTest(selector=selector):
                self.assertNotIn(selector, css)

    def test_professional_claims_render_from_central_doctor_context(self):
        doctor = Doctor.objects.create(
            full_name_ar="طبيب مركزي معتمد",
            full_name_en="Central Approved Doctor",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="تخصص مركزي معتمد",
            specialty_en="Central approved specialty",
            bio_ar="نبذة مركزية معتمدة من بيانات الطبيب.",
            bio_en="Central approved doctor profile copy.",
            is_active=True,
        )

        response = self.client.get(reverse("home_en"))
        html = response.content.decode()
        doctor_context = response.context["doctor"]

        self.assertIn(doctor.specialty_en, html)
        self.assertIn(doctor.bio_en, html)
        self.assertIn(doctor_context["credential_label_en"].replace("&", "&amp;"), html)
        self.assertIn(doctor_context["public_focus_en"].replace("&", "&amp;"), html)
        self.assertIn(doctor_context["hero_summary_en"], html)

        template_claims = {
            settings.BASE_DIR / "templates" / "core" / "home.html": [
                "European ENT Board",
                "functional and cosmetic rhinoplasty",
            ],
            settings.BASE_DIR / "templates" / "partials" / "header.html": [
                "ENT & Functional and Cosmetic Rhinoplasty",
            ],
            settings.BASE_DIR / "templates" / "partials" / "footer.html": [
                "Adult and pediatric ear, nose and throat medicine and surgery",
                "functional and cosmetic rhinoplasty",
            ],
        }
        for template_path, claims in template_claims.items():
            source = template_path.read_text(encoding="utf-8")
            for claim in claims:
                with self.subTest(template=template_path.name, claim=claim):
                    self.assertNotIn(claim, source)

    def test_case_carousel_uses_logical_rtl_safe_element_scrolling(self):
        javascript = (settings.BASE_DIR / "static" / "js" / "site.js").read_text(encoding="utf-8")

        self.assertIn("scrollIntoView", javascript)
        self.assertIn('inline: "start"', javascript)
        self.assertIn("getComputedStyle(caseCarousel).direction", javascript)
        self.assertIn('const effectiveBehavior = reducedMotion ? "auto" : behavior;', javascript)
        self.assertIn("behavior: effectiveBehavior", javascript)
        self.assertNotIn("caseCarousel.scrollTo", javascript)
        self.assertNotIn("offsetLeft", javascript)

    def test_case_carousel_autoplays_across_viewports_and_preserves_motion_controls(self):
        javascript = (settings.BASE_DIR / "static" / "js" / "site.js").read_text(encoding="utf-8")
        css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(encoding="utf-8")

        self.assertIn("!reducedMotion && !paused && cards.length > 1", javascript)
        self.assertNotIn("window.innerWidth < 768", javascript)
        self.assertIn('window.matchMedia("(min-width: 1024px)")', javascript)
        self.assertIn("const rotateDesktopCards", javascript)
        self.assertIn("const orderedCards = cards.slice(startIndex).concat", javascript)
        self.assertIn("orderedCards.forEach((card) => caseCarousel.append(card))", javascript)
        self.assertIn("const restoreOriginalCardOrder", javascript)
        self.assertIn("cards.forEach((card) => caseCarousel.append(card))", javascript)
        self.assertIn("if (desktopCaseLayout.matches)", javascript)
        self.assertIn('caseCarousel.addEventListener("pointerenter"', javascript)
        self.assertIn('caseCarousel.addEventListener("pointerleave"', javascript)
        self.assertIn('caseCarousel.addEventListener("focusin"', javascript)
        self.assertIn('caseCarousel.addEventListener("focusout"', javascript)
        self.assertIn('pauseAutoplay("hover")', javascript)
        self.assertIn('pauseAutoplay("focus")', javascript)
        self.assertIn('pauseAutoplay("pointer")', javascript)
        self.assertIn('card.classList.toggle("is-active", isActive)', javascript)
        self.assertIn(".case-card.is-active", css)
        reduced_motion_css = css[css.index("@media (prefers-reduced-motion: reduce)") :]
        self.assertIn(".case-card,", reduced_motion_css)
        self.assertIn("transition: none;", reduced_motion_css)

    def test_home_sections_follow_locked_order_and_review_surface_is_empty(self):
        arabic = self.client.get(reverse("home"))
        english = self.client.get(reverse("home_en"))
        html = arabic.content.decode()
        css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(encoding="utf-8")
        ordered_markers = [
            '<section class="home-hero"',
            '<section class="section home-doctor"',
            '<section class="section home-cases"',
            'id="reviews"',
            '<section class="section home-contact"',
            '<section class="section home-faq"',
            '<footer class="site-footer"',
        ]

        positions = [html.index(marker) for marker in ordered_markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('data-review-surface="empty"', html)
        self.assertNotIn('hidden aria-hidden="true"', html)
        self.assertContains(arabic, "آراء المرضى")
        self.assertContains(arabic, "ستظهر تقييمات المرضى المعتمدة هنا.")
        self.assertContains(english, "Patient Reviews")
        self.assertContains(english, "Approved patient reviews will appear here.")
        for response in [arabic, english]:
            response_html = response.content.decode()
            self.assertIn('data-review-empty', response_html)
            self.assertNotIn('data-review-card', response_html)
            self.assertNotIn('data-review-summary', response_html)
            self.assertNotIn('class="section home-services"', response_html)
            self.assertNotIn("Patient Stories", response_html)
            self.assertNotIn("قصص المرضى", response_html)
            self.assertNotIn("Testimonials", response_html)
            self.assertNotIn("4.8", response_html)
            self.assertNotIn("174", response_html)
        self.assertIn(".home-hero-visual {\n    display: none;", css)
        self.assertIn(".home-faq {\n    display: none;", css)
        self.assertIn('.home-reviews[data-review-surface="empty"]', css)
        self.assertIn(".home-reviews-empty", css)

    def test_home_has_responsive_hooks_without_scale_workaround(self):
        response = self.client.get(reverse("home_en"))
        html = response.content.decode()
        css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(encoding="utf-8")

        self.assertIn('data-hero-carousel', html)
        self.assertIn('class="home-hero-visual"', html)
        self.assertIn('class="section home-reviews"', html)
        self.assertIn('class="section home-faq"', html)
        self.assertIn('@media (min-width: 768px)', css)
        self.assertIn('.home-faq {\n        display: block;', css)
        self.assertNotIn('.home-reviews[hidden]', css)
        self.assertNotIn('.home-services', css)
        self.assertNotIn('transform: scale(', css.casefold())

    def test_doctor_page_renders_backend_identity_and_approved_owner_profile(self):
        doctor = Doctor.objects.create(
            full_name_ar="طبيب عربي معتمد",
            full_name_en="Approved Backend Doctor",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="تخصص معتمد من الخلفية",
            specialty_en="Backend-approved specialty",
            bio_ar="نبذة عربية معتمدة من الخلفية فقط.",
            bio_en="Backend-approved profile copy only.",
            is_active=True,
        )

        response = self.client.get(reverse("doctor_en"))

        self.assertContains(response, doctor.display_name_en)
        self.assertContains(response, doctor.specialty_en)
        self.assertContains(response, doctor.bio_en)
        approved_profile_copy = [
            "Professional Profile",
            "Professional Experience",
            "Education & Training",
            "Boards / Certifications",
            "Professional Memberships",
            "Specialties",
            "Conditions Treated",
            "Awards",
            "Languages",
            "European Board Certificate — ENT (EBC)",
            "Jordanian Board Certificate — ENT (JBC)",
            "FRCSI",
            "GMC",
            "BAO-HNS",
            "MDU",
            "MRCSI",
            "Higher Specialization — University of Jordan",
            "Bachelor of Medicine and Surgery — University of Jordan",
            "University of Central Lancashire, United Kingdom",
            "Monklands Hospital, United Kingdom",
            "Four years of ENT consultant experience in a UK hospital.",
            "Specialist registrar experience across multiple UK hospitals.",
            "King Hussein Cancer Center Award — 2015",
            "Presidential Candidate Award — 2011",
            "Arabic",
            "English",
        ]
        for approved_value in approved_profile_copy:
            with self.subTest(value=approved_value):
                self.assertContains(response, approved_value)

    def test_doctor_awards_and_languages_are_inside_the_professional_composition(self):
        response = self.client.get(reverse("doctor_en"))
        html = response.content.decode()
        professional_start = html.index('class="section doctor-details-section"')
        clinical_start = html.index('class="section doctor-clinical-section"')
        professional_html = html[professional_start:clinical_start]

        ordered_headings = [
            "Professional Experience",
            "Education & Training",
            "Boards / Certifications",
            "Professional Memberships",
            "Awards",
            "Languages",
        ]
        heading_positions = [professional_html.index(heading) for heading in ordered_headings]
        self.assertEqual(heading_positions, sorted(heading_positions))
        self.assertIn('class="doctor-detail-card doctor-awards-card"', professional_html)
        self.assertIn('class="doctor-detail-card doctor-languages-card"', professional_html)
        self.assertNotIn("doctor-recognition-section", html)
        self.assertNotIn("doctor-recognition-card", html)

    def test_doctor_professional_experience_and_education_preserve_all_owner_facts(self):
        arabic = self.client.get(reverse("doctor"))
        english = self.client.get(reverse("doctor_en"))

        expected_experience_ar = [
            "الدكتور خالد يعمل حالياً في عيادته الخاصة في عمّان.",
            "زمالة/تدريب في الأنف والأذن والحنجرة في مستشفى مونكلاندز، المملكة المتحدة.",
            "عمل لمدة أربعة أعوام كمستشار في اختصاص الأنف والأذن والحنجرة في مستشفى الوادي الرابع الملكي",
            "عمل كطبيب اختصاصي مسجل في عدد كبير من المستشفيات البريطانية.",
        ]
        expected_experience_en = [
            "Dr. Khaled currently works in his private clinic in Amman.",
            "ENT fellowship/training at Monklands Hospital, United Kingdom.",
            "Four years of ENT consultant experience in a UK hospital.",
            "Specialist registrar experience across multiple UK hospitals.",
        ]
        expected_education_ar = [
            "بكالوريوس الطب والجراحة — الجامعة الأردنية، الأردن",
            "ماجستير في العلوم الصحية — جامعة لانكشاير المركزية، المملكة المتحدة",
            "زمالة — أنف وأذن وحنجرة — مستشفى مونكلاندز، المملكة المتحدة",
            "تخصص — أنف وأذن وحنجرة — مستشفى الجامعة الأردنية، الأردن",
            "الاختصاص العالي — الجامعة الأردنية",
        ]
        expected_education_en = [
            "Bachelor of Medicine and Surgery — University of Jordan, Jordan",
            "Master’s in Health Sciences — University of Central Lancashire, United Kingdom",
            "ENT Fellowship — Monklands Hospital, United Kingdom",
            "ENT Specialization — University of Jordan Hospital, Jordan",
            "Higher Specialization — University of Jordan",
        ]

        self.assertEqual(arabic.context["doctor_profile"]["experience"], expected_experience_ar)
        self.assertEqual(english.context["doctor_profile"]["experience"], expected_experience_en)
        self.assertEqual(arabic.context["doctor_profile"]["education"], expected_education_ar)
        self.assertEqual(english.context["doctor_profile"]["education"], expected_education_en)
        for response, expected_items in [
            (arabic, expected_experience_ar + expected_education_ar),
            (english, expected_experience_en + expected_education_en),
        ]:
            for item in expected_items:
                with self.subTest(language=response.context["language"], item=item):
                    self.assertContains(response, item)

    def test_doctor_boards_memberships_and_six_specialties_match_owner_content(self):
        arabic = self.client.get(reverse("doctor"))
        english = self.client.get(reverse("doctor_en"))

        expected_boards_ar = [
            "شهادة البورد الأوروبي — أنف وأذن وحنجرة (EBC)",
            "شهادة البورد الأردني — أنف وأذن وحنجرة (JBC)",
        ]
        expected_boards_en = [
            "European Board Certificate — ENT (EBC)",
            "Jordanian Board Certificate — ENT (JBC)",
        ]
        expected_membership_labels_ar = [
            "الكلية الملكية للجراحين - أيرلندا",
            "المجلس الطبي العام البريطاني",
            "الأكاديمية الأمريكية لجراحة الأنف والأذن والحنجرة والرأس والرقبة",
            "اتحاد الدفاع الطبي",
            "عضو الكلية الملكية للجراحين - أيرلندا",
        ]
        expected_acronyms = ["FRCSI", "GMC", "BAO-HNS", "MDU", "MRCSI"]
        expected_specialties_ar = [
            "أنف وأذن وحنجرة",
            "أنف وأذن وحنجرة كبار",
            "أنف وأذن وحنجرة أطفال",
            "جراحة أنف وأذن وحنجرة كبار",
            "جراحة أنف وأذن وحنجرة أطفال",
            "جراحة تجميل الأنف",
        ]
        expected_specialties_en = [
            "Ear, Nose and Throat",
            "Adult ENT",
            "Pediatric ENT",
            "Adult ENT Surgery",
            "Pediatric ENT Surgery",
            "Rhinoplasty",
        ]

        self.assertEqual(arabic.context["doctor_profile"]["boards"], expected_boards_ar)
        self.assertEqual(english.context["doctor_profile"]["boards"], expected_boards_en)
        self.assertEqual(len(arabic.context["doctor_profile"]["memberships"]), 5)
        self.assertEqual(len(english.context["doctor_profile"]["memberships"]), 5)
        self.assertEqual(
            [item["label"] for item in arabic.context["doctor_profile"]["memberships"]],
            expected_membership_labels_ar,
        )
        self.assertEqual(
            [item["acronym"] for item in arabic.context["doctor_profile"]["memberships"]],
            expected_acronyms,
        )
        self.assertEqual(
            [item["acronym"] for item in english.context["doctor_profile"]["memberships"]],
            expected_acronyms,
        )
        self.assertEqual(arabic.context["doctor_profile"]["specialties"], expected_specialties_ar)
        self.assertEqual(english.context["doctor_profile"]["specialties"], expected_specialties_en)

        for response, expected_items in [
            (arabic, expected_boards_ar + expected_membership_labels_ar + expected_acronyms + expected_specialties_ar),
            (english, expected_boards_en + expected_acronyms + expected_specialties_en),
        ]:
            for item in expected_items:
                with self.subTest(language=response.context["language"], item=item):
                    self.assertContains(response, item)

    def test_doctor_conditions_use_dedicated_owner_source_not_service_groups(self):
        expected_ar = [
            "التهاب الجيوب الأنفية المزمن",
            "الرشح",
            "طنين الأذن",
            "ألم الأذن",
            "الحالات الطارئة لأمراض الأنف والأذن والحنجرة",
            "الشخير",
            "التهاب الأذن",
            "التهاب الحلق المزمن",
            "التهاب الحنجرة",
            "التهاب اللوزتين عند الكبار",
            "لحمية الأنف (سليلة أنفية)",
        ]
        expected_en = [
            "Chronic sinusitis",
            "Common cold",
            "Tinnitus",
            "Ear pain",
            "ENT emergencies",
            "Snoring",
            "Ear infection",
            "Chronic sore throat",
            "Laryngitis",
            "Adult tonsillitis",
            "Nasal polyps (nasal polyp)",
        ]
        arabic = self.client.get(reverse("doctor"))
        english = self.client.get(reverse("doctor_en"))

        self.assertEqual(core_views.DOCTOR_CONDITIONS["ar"], expected_ar)
        self.assertEqual(core_views.DOCTOR_CONDITIONS["en"], expected_en)
        self.assertEqual(arabic.context["doctor_profile"]["conditions"], expected_ar)
        self.assertEqual(english.context["doctor_profile"]["conditions"], expected_en)
        self.assertNotEqual(arabic.context["doctor_profile"]["conditions"], core_views.SERVICE_GROUPS["ar"])
        self.assertNotEqual(english.context["doctor_profile"]["conditions"], core_views.SERVICE_GROUPS["en"])

        views_source = (settings.BASE_DIR / "apps" / "core" / "views.py").read_text(encoding="utf-8")
        self.assertIn('"conditions": DOCTOR_CONDITIONS[language]', views_source)
        self.assertNotIn('"conditions": SERVICE_GROUPS[language]', views_source)
        for response, expected_items in [(arabic, expected_ar), (english, expected_en)]:
            for item in expected_items:
                with self.subTest(language=response.context["language"], item=item):
                    self.assertContains(response, item)

    def test_doctor_awards_and_languages_use_approved_bilingual_content(self):
        arabic = self.client.get(reverse("doctor"))
        english = self.client.get(reverse("doctor_en"))

        self.assertEqual(
            arabic.context["doctor_profile"]["awards"],
            ["جائزة مركز الحسين للسرطان — 2015", "جائزة المرشح الرئاسي — 2011"],
        )
        self.assertEqual(
            english.context["doctor_profile"]["awards"],
            ["King Hussein Cancer Center Award — 2015", "Presidential Candidate Award — 2011"],
        )
        self.assertEqual(arabic.context["doctor_profile"]["languages"], ["العربية", "الإنجليزية"])
        self.assertEqual(english.context["doctor_profile"]["languages"], ["Arabic", "English"])
        self.assertContains(arabic, "جائزة المرشح الرئاسي — 2011")
        self.assertNotContains(arabic, "Presidential Candidate Award")
        self.assertContains(english, "Presidential Candidate Award — 2011")

    def test_public_backgrounds_share_geometry_and_exclude_placeholder_cross_motif(self):
        css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(encoding="utf-8")

        self.assertIn(".public-shell.is-rtl .home-hero", css)
        self.assertIn(".public-shell.is-rtl .page-hero", css)
        self.assertNotIn("clinic-placeholder.svg", css)
        self.assertNotIn("calc(100vh", css)

    def test_clinic_gallery_uses_only_approved_unique_public_asset_paths(self):
        approved_assets = [
            "img/clinic/clinic-interior-1.png",
            "img/clinic/clinic-interior-2.png",
            "img/clinic/clinic-interior-3.png",
            "img/clinic/clinic-interior-4.webp",
            "img/clinic/clinic-interior-5.webp",
        ]
        configured_assets = [
            photo["asset_path"] for photo in core_views.APPROVED_PUBLIC_CLINIC_GALLERY
        ]
        contact_source = (settings.BASE_DIR / "templates" / "core" / "contact.html").read_text(
            encoding="utf-8"
        )
        views_source = (settings.BASE_DIR / "apps" / "core" / "views.py").read_text(
            encoding="utf-8"
        )

        self.assertEqual(configured_assets, approved_assets)
        self.assertEqual(len(configured_assets), 5)
        self.assertEqual(len(set(configured_assets)), len(configured_assets))
        self.assertEqual(
            core_views.APPROVED_PUBLIC_CLINIC_GALLERY[0]["asset_path"],
            "img/clinic/clinic-interior-1.png",
        )
        self.assertEqual(
            core_views.APPROVED_PUBLIC_CLINIC_GALLERY[0]["alt_en"],
            "Reception area inside Dr. Khaled Badran Clinic",
        )
        for asset_path in approved_assets:
            with self.subTest(asset=asset_path):
                self.assertTrue((settings.BASE_DIR / "static" / asset_path).is_file())

        for route_name in ["contact", "contact_en"]:
            html = self.client.get(reverse(route_name)).content.decode()
            with self.subTest(route=route_name):
                for asset_path in approved_assets:
                    self.assertIn(asset_path, html)
                gallery_html = html[html.index("data-clinic-gallery") :]
                asset_positions = [gallery_html.index(asset_path) for asset_path in approved_assets]
                self.assertEqual(asset_positions, sorted(asset_positions))
                primary_marker = gallery_html.index("data-gallery-primary")
                first_asset_position = gallery_html.index(approved_assets[0])
                second_asset_position = gallery_html.index(approved_assets[1])
                self.assertLess(primary_marker, first_asset_position)
                self.assertLess(first_asset_position, second_asset_position)
                self.assertNotIn("clinic-placeholder.svg", html)
                self.assertNotIn("unnamed (2).webp", html)
                self.assertNotIn("unnamed (5).webp", html)

        for route_name in ["home", "home_en"]:
            html = self.client.get(reverse(route_name)).content.decode()
            with self.subTest(route=route_name):
                for asset_path in approved_assets[:3]:
                    self.assertIn(asset_path, html)
                self.assertNotIn("clinic-placeholder.svg", html)

        for excluded_source_name in ["unnamed (2).webp", "unnamed (5).webp"]:
            with self.subTest(excluded=excluded_source_name):
                self.assertNotIn(excluded_source_name, contact_source)
                self.assertNotIn(excluded_source_name, views_source)

    def test_clinic_gallery_responsive_contract_has_three_desktop_and_one_mobile_card(self):
        response = self.client.get(reverse("contact_en"))
        html = response.content.decode()
        css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("data-clinic-gallery", html)
        self.assertEqual(html.count("data-gallery-slide"), 5)
        self.assertEqual(html.count("data-gallery-dot="), 5)
        self.assertIn("data-gallery-previous", html)
        self.assertIn("data-gallery-next", html)
        mobile_css = css[: css.index("@media (min-width: 768px)")]
        self.assertIn(".clinic-gallery-slide {\n    flex: 0 0 100%;", mobile_css)
        self.assertIn(".clinic-gallery-viewport {\n    width: 100%;", mobile_css)
        self.assertIn("overflow-x: auto", mobile_css)
        self.assertIn("scroll-snap-type: inline mandatory", mobile_css)
        self.assertIn("touch-action: pan-x pan-y", mobile_css)

        desktop_css = css[css.index("@media (min-width: 768px)") :]
        self.assertIn(
            ".clinic-gallery-viewport {\n"
            "        overflow: visible;\n"
            "        scroll-snap-type: none;\n"
            "        touch-action: auto;",
            desktop_css,
        )
        self.assertIn(
            ".clinic-gallery-track {\n"
            "        display: grid;\n"
            "        width: 100%;\n"
            "        grid-template-columns: repeat(3, minmax(0, 1fr));",
            desktop_css,
        )
        self.assertIn(
            ".clinic-gallery-slide {\n"
            "        width: 100%;\n"
            "        flex: none;\n"
            "        scroll-snap-align: none;",
            desktop_css,
        )
        self.assertIn(
            ".clinic-gallery-slide:nth-child(n + 4) {\n        display: none;",
            desktop_css,
        )
        self.assertNotIn("flex-basis: calc((100% - 2rem) / 3)", desktop_css)
        self.assertIn("max-width: 100%", css)
        self.assertIn("min-width: 0", css)
        self.assertIn(".clinic-gallery-viewport {\n        scroll-behavior: auto;", css)
        self.assertNotIn("transform: scale(", css.casefold())

    def test_clinic_gallery_runtime_autoplay_pause_resume_and_reduced_motion(self):
        runtime_test = settings.BASE_DIR / "apps" / "core" / "js_tests" / "clinic_gallery_runtime_test.js"
        site_script = settings.BASE_DIR / "static" / "js" / "site.js"

        result = subprocess.run(
            ["node", str(runtime_test), str(site_script)],
            cwd=settings.BASE_DIR,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"JavaScript gallery behavior failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("clinic gallery runtime behavior passed", result.stdout)

    def test_public_footer_is_concise_complete_and_uses_one_emergency_sentence(self):
        response = self.client.get(reverse("home_en"))
        html = response.content.decode()

        self.assertContains(
            response,
            "Consultant Ear, Nose and Throat Surgeon · Functional and Cosmetic Rhinoplasty",
        )
        self.assertContains(response, "Book an Appointment")
        self.assertContains(response, "Patient Portal")
        self.assertContains(response, "+962 7 8976 6332")
        self.assertContains(response, "The website and WhatsApp are not for emergencies.", count=1)
        self.assertNotIn("For urgent symptoms, contact local emergency services immediately.", html)

        footer_source = (settings.BASE_DIR / "templates" / "partials" / "footer.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("doctor.bio_", footer_source)

    def test_unsupported_figma_claims_are_absent_from_public_pages(self):
        route_names = [
            "home",
            "home_en",
            "doctor",
            "doctor_en",
            "contact",
            "contact_en",
        ]
        blocked_copy = ["world-class", "15+ years", "Dubai", "best clinic", "guaranteed"]

        for route_name in route_names:
            response_text = self.client.get(reverse(route_name)).content.decode().casefold()
            for blocked in blocked_copy:
                with self.subTest(route=route_name, blocked=blocked):
                    self.assertNotIn(blocked.casefold(), response_text)

    @override_settings(DEBUG=False)
    def test_branded_404_is_bilingual_and_design_system_is_not_exposed(self):
        arabic = self.client.get("/missing-public-page/")
        english = self.client.get("/en/missing-public-page/")
        design_system = self.client.get("/design-system/")

        self.assertEqual(arabic.status_code, 404)
        self.assertContains(arabic, "الصفحة غير موجودة", status_code=404)
        self.assertContains(arabic, "عيادة الدكتور خالد بدران", status_code=404)
        self.assertEqual(english.status_code, 404)
        self.assertContains(english, "Page Not Found", status_code=404)
        self.assertContains(english, "Dr. Khaled Badran Clinic", status_code=404)
        self.assertEqual(design_system.status_code, 404)
        self.assertNotContains(design_system, "Design System", status_code=404)

    def test_sitemap_uses_contact_location_and_never_lists_design_system(self):
        response = self.client.get(reverse("sitemap_xml"))
        content = response.content.decode()

        self.assertIn("/contact-location/", content)
        self.assertIn("/en/contact-location/", content)
        self.assertNotIn("/design-system", content)
