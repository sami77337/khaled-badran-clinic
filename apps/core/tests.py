import json
import os
import re
import uuid
from datetime import date, timedelta
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
from apps.core.checks import production_readiness_checks
from apps.patients.models import Patient
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord
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
        self.assertIn(reverse("patient_portal_login"), response["Location"])

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
        self.assertIn(reverse("patient_portal_login"), response["Location"])


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

    def create_media(
        self,
        *,
        patient=None,
        visit=None,
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
        return RecordMedia.objects.create(
            patient=patient,
            visit=visit,
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
        self.assertContains(response, "No approved public showcase media yet")
        self.assertContains(response, "Approved and consented content only")
        self.assertNotContains(response, "<form")
        self.assertNotContains(response, "upload")
        self.assertNotContains(response, str(settings.PRIVATE_MEDIA_ROOT))

    def test_only_approved_consented_active_public_case_media_appears(self):
        approved_image = self.create_media(
            title="Approved public image title",
            description="Approved public image description.",
            file=self.synthetic_image_file(name="synthetic-public-case.jpg"),
        )
        approved_video = self.create_media(
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            title="Approved public short video title",
            description="Approved public short video description.",
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

        self.assertContains(response, "Approved public image title")
        self.assertContains(response, "Approved public image description.")
        self.assertContains(response, "Approved public short video title")
        self.assertContains(response, "Approved public short video description.")
        self.assertContains(
            response,
            f'href="{reverse("public_case_media_en", kwargs={"public_id": approved_image.public_id})}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("public_case_media_en", kwargs={"public_id": approved_video.public_id})}"',
        )
        self.assertNotContains(response, "Private-only media must stay hidden")
        self.assertNotContains(response, "Patient-visible media must stay hidden")
        self.assertNotContains(response, "Inactive public case media must stay hidden")
        self.assertNotContains(response, "Unconsented public case media must stay hidden")
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
        media = self.create_media(
            patient=patient,
            visit=visit,
            title="Approved public case metadata only",
            description="Approved public case description only.",
        )

        response = self.client.get(reverse("public_cases_en"))

        self.assertContains(response, "Approved public case metadata only")
        self.assertContains(response, "Approved public case description only.")
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
            media.file.name,
            str(settings.PRIVATE_MEDIA_ROOT),
        ]
        for fragment in blocked_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotContains(response, fragment)

    def test_home_teaser_uses_public_case_route_only(self):
        media = self.create_media(
            title="Home approved public case teaser",
            description="Home approved public case teaser description.",
            file=self.synthetic_image_file(name="synthetic-public-case.jpg"),
        )
        self.create_media(
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Home patient-visible teaser must stay hidden",
        )

        response = self.client.get(reverse("home_en"))

        self.assertContains(response, "Home approved public case teaser")
        self.assertContains(response, reverse("public_cases_en"))
        self.assertContains(
            response,
            reverse("public_case_media_en", kwargs={"public_id": media.public_id}),
        )
        self.assertNotContains(response, "Home patient-visible teaser must stay hidden")
        self.assertNotContains(response, media.file.name)
        self.assertNotContains(response, "synthetic-public-case.jpg")
        self.assertNotContains(response, str(settings.PRIVATE_MEDIA_ROOT))


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


class PublicCasesRegressionBoundaryTests(PublicCasesTestDataMixin, TestCase):
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
        self.assertIn(reverse("admin:login"), anonymous_response["Location"])
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
    def test_public_language_direction_is_natural_for_arabic_and_english(self):
        arabic = self.client.get(reverse("home"))
        english = self.client.get(reverse("home_en"))

        self.assertContains(arabic, '<html lang="ar" dir="rtl">')
        self.assertContains(english, '<html lang="en" dir="ltr">')

    def test_contact_location_is_canonical_and_legacy_contact_routes_redirect(self):
        self.assertEqual(reverse("contact"), "/contact-location/")
        self.assertEqual(reverse("contact_en"), "/en/contact-location/")

        arabic = self.client.get("/contact/", follow=False)
        english = self.client.get("/en/contact/", follow=False)

        self.assertEqual(arabic.status_code, 301)
        self.assertEqual(arabic["Location"], "/contact-location/")
        self.assertEqual(english.status_code, 301)
        self.assertEqual(english["Location"], "/en/contact-location/")

    def test_contact_location_uses_approved_map_and_hides_unconfigured_contact_rows(self):
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
        self.assertContains(response, "رابط واتساب السريع غير مفعّل")
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

    def test_home_sections_follow_locked_order_and_review_surface_is_empty(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode()
        ordered_markers = [
            '<section class="home-hero"',
            '<section class="section home-doctor"',
            '<section class="section home-cases"',
            '<section class="section home-services"',
            '<section id="reviews"',
            '<section class="section home-contact"',
            '<footer class="site-footer"',
        ]

        positions = [html.index(marker) for marker in ordered_markers]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('data-review-surface="empty" aria-hidden="true"></section>', html)
        self.assertNotIn("Patient Stories", html)
        self.assertNotIn("قصص المرضى", html)
        self.assertNotIn("Testimonials", html)

    def test_home_has_responsive_hooks_without_scale_workaround(self):
        response = self.client.get(reverse("home_en"))
        html = response.content.decode()
        css = (settings.BASE_DIR / "static" / "css" / "public.css").read_text(encoding="utf-8")

        self.assertIn('data-hero-carousel', html)
        self.assertIn('class="home-hero-visual"', html)
        self.assertIn('class="section home-services"', html)
        self.assertIn('class="section home-faq"', html)
        self.assertIn('@media (min-width: 768px)', css)
        self.assertIn('.home-services,\n    .home-faq {\n        display: block;', css)
        self.assertNotIn('transform: scale(', css.casefold())

    def test_doctor_page_renders_existing_backend_doctor_fields_only(self):
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
        for unsupported_profile_field in ["FRCSI", "MRCSI", "GMC", "MDU", "Bachelor of Medicine"]:
            with self.subTest(field=unsupported_profile_field):
                self.assertNotContains(response, unsupported_profile_field)

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
