import json
import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import ignore_warnings
from django.urls import reverse

from apps.booking.models import Appointment
from apps.core.checks import production_readiness_checks
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
        self.assertEqual(settings.CACHES["default"]["BACKEND"], "django.core.cache.backends.locmem.LocMemCache")


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

    def test_patient_portal_account_security_routes_are_summarized(self):
        output = self.call_smoke(json_output=True)
        payload = json.loads(output)
        portal_check = next(
            check for check in payload["checks"] if check["name"] == "patient_portal_security_summary"
        )

        self.assertTrue(portal_check["details"]["account_security_routes"])
        self.assertFalse(portal_check["details"]["email_password_reset_enabled"])

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


class OperationalDocumentationTests(SimpleTestCase):
    docs_dir = Path(settings.BASE_DIR) / "docs"

    def read_doc(self, name):
        return (self.docs_dir / name).read_text(encoding="utf-8")

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

        self.assertIn("patient portal remains bounded to account security and linked-appointment viewing", content)
        self.assertIn("logged-in password change uses Django validation/hashing", content)
        self.assertIn("account recovery is clinic-assisted", content)
        self.assertIn("no uploads until private media design exists", content)
        self.assertIn("no WhatsApp until consent/logging/cost/security design exists", content)
        self.assertIn("no medical records until authorization/audit/patient visibility rules are tested", content)

    def test_ci_workflow_runs_deployment_smoke(self):
        workflow = Path(settings.BASE_DIR, ".github", "workflows", "django.yml").read_text(encoding="utf-8")

        self.assertIn("python manage.py deployment_smoke", workflow)


class PortalFoundationRouteTests(TestCase):
    def test_patient_portal_requires_authentication(self):
        response = self.client.get("/portal/")

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("patient_portal_login"), response["Location"])

    def test_upload_and_whatsapp_routes_remain_absent(self):
        blocked_paths = [
            "/uploads/",
            "/portal/uploads/",
            "/whatsapp/webhook/",
            "/api/whatsapp/",
            "/records/",
            "/medical-records/",
            "/portal/medical-records/",
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
            "contact",
            "privacy",
            "terms",
            "medical_disclaimer",
            "whatsapp_policy",
            "home_en",
            "doctor_en",
            "services_en",
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
