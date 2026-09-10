"""Synthetic fixtures only; every provider HTTP connection is mocked."""

from datetime import timedelta
import json
import logging
from unittest.mock import patch
import uuid

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import meta
from .checks import meta_configuration_checks
from .logging import WebhookPrivacyFilter
from .notifications import REPLY_MESSAGES


META_SETTINGS = {
    "WHATSAPP_META_ENABLED": True,
    "WHATSAPP_META_ACCESS_TOKEN": "synthetic-access-token",
    "WHATSAPP_META_APP_SECRET": "synthetic-app-secret",
    "WHATSAPP_META_VERIFY_TOKEN": "synthetic-verify-token",
    "WHATSAPP_META_PHONE_NUMBER_ID": "101",
    "WHATSAPP_META_WABA_ID": "202",
    "WHATSAPP_META_GRAPH_VERSION": "v999.0",  # Deliberately invented, never a production default.
    "WHATSAPP_WEBSITE_ORIGIN": "https://clinic.example.test",
    "WHATSAPP_META_OTP_TEMPLATE": "synthetic_otp",
    "WHATSAPP_META_CONSULTATION_REPLY_TEMPLATE": "synthetic_reply",
    "WHATSAPP_META_BOOKING_CONFIRMATION_TEMPLATE": "synthetic_confirmation",
    "WHATSAPP_META_APPOINTMENT_REMINDER_TEMPLATE": "synthetic_reminder",
    "WHATSAPP_META_LOCATION_TEMPLATE": "synthetic_location",
    "WHATSAPP_META_TEMPLATE_LANGUAGE_AR": "ar",
    "WHATSAPP_META_TEMPLATE_LANGUAGE_EN": "en_US",
    "GUEST_CONSULTATION_OTP_SENDER": "apps.whatsapp.meta.send_guest_otp",
    "WHATSAPP_CONSULTATION_NOTIFICATION_SENDER": "apps.whatsapp.meta.send_consultation_notification",
    "WHATSAPP_DEFAULT_LANGUAGE": "ar",
}
SYNTHETIC_PHONE = "+12025550101"  # Reserved fictional NANP number.


@override_settings(**META_SETTINGS)
class MetaAdapterTests(SimpleTestCase):
    def setUp(self):
        self.http = patch("apps.whatsapp.meta.http.client.HTTPSConnection").start()
        self.addCleanup(patch.stopall)
        self.connection = self.http.return_value
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.response.read.return_value = (
            b'{"messages":[{"id":"synthetic-message-id"}]}'
        )

    def payload(self):
        return json.loads(self.connection.request.call_args.kwargs["body"])

    def test_authentication_template_otp_body_and_copy_button_in_both_languages(self):
        for language, code in (("ar", "ar"), ("en", "en_US")):
            with self.subTest(language=language):
                self.assertTrue(
                    meta.send_guest_otp(SYNTHETIC_PHONE, "012345", language)
                )
                payload = self.payload()
                self.assertEqual(payload["type"], "template")
                self.assertEqual(payload["to"], SYNTHETIC_PHONE.lstrip("+"))
                self.assertEqual(
                    payload["template"],
                    {
                        "name": "synthetic_otp",
                        "language": {"code": code},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [{"type": "text", "text": "012345"}],
                            },
                            {
                                "type": "button",
                                "sub_type": "url",
                                "index": "0",
                                "parameters": [{"type": "text", "text": "012345"}],
                            },
                        ],
                    },
                )
                self.http.assert_called_with("graph.facebook.com", timeout=8)
                self.assertEqual(
                    self.connection.request.call_args.args,
                    ("POST", "/v999.0/101/messages"),
                )

    def test_template_name_and_language_are_configurable(self):
        with self.settings(
            WHATSAPP_META_OTP_TEMPLATE="synthetic_alternate",
            WHATSAPP_META_TEMPLATE_LANGUAGE_EN="en_GB",
        ):
            self.assertTrue(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "en"))
            self.assertEqual(self.payload()["template"]["name"], "synthetic_alternate")
            self.assertEqual(self.payload()["template"]["language"]["code"], "en_GB")

    def test_invalid_otp_is_not_sent(self):
        for code in ("", "12345", "1234567", "private-payload-sentinel", 123456):
            self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, code, "ar"))
        self.http.assert_not_called()

    def test_missing_or_invalid_configuration_fails_without_http(self):
        for key in (
            "WHATSAPP_META_ACCESS_TOKEN",
            "WHATSAPP_META_PHONE_NUMBER_ID",
            "WHATSAPP_META_WABA_ID",
            "WHATSAPP_META_APP_SECRET",
            "WHATSAPP_META_VERIFY_TOKEN",
            "WHATSAPP_META_GRAPH_VERSION",
            "WHATSAPP_WEBSITE_ORIGIN",
            "WHATSAPP_META_OTP_TEMPLATE",
            "WHATSAPP_META_TEMPLATE_LANGUAGE_AR",
        ):
            with self.subTest(key=key), self.settings(**{key: ""}):
                self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
        with self.settings(WHATSAPP_META_ENABLED=False):
            self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
        for version in ("v999.0/elsewhere", "https://example.test", "v999.0?token=x"):
            with self.settings(WHATSAPP_META_GRAPH_VERSION=version):
                self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
        self.http.assert_not_called()

    def test_configuration_check_reports_names_never_values(self):
        self.assertEqual(meta_configuration_checks(None), [])
        with self.settings(WHATSAPP_META_GRAPH_VERSION="synthetic-secret-value"):
            issues = meta_configuration_checks(None)
            self.assertEqual(issues[0].id, "whatsapp.E001")
            self.assertIn("WHATSAPP_META_GRAPH_VERSION", issues[0].hint)
            self.assertNotIn("synthetic-secret-value", str(issues))
        with self.settings(
            PRODUCTION=True,
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}},
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
            },
        ):
            self.assertIn("PostgreSQL", str(meta_configuration_checks(None)))
            self.assertIn("shared", str(meta_configuration_checks(None)))

    def test_invalid_website_origins_and_default_language_fail_without_http(self):
        for origin in (
            "https://clinic.example.test:invalid",
            "https://clinic.example.test:65536",
            "https://clinic.example.test:0",
            "https://clinic.example.test/extra",
            "https://clinic.example.test\n",
            "https://clinic.example.test\\other",
            "https://user:password@clinic.example.test",
            "http://clinic.example.test",
        ):
            with self.settings(WHATSAPP_WEBSITE_ORIGIN=origin):
                issues = meta_configuration_checks(None)
                self.assertIn("WHATSAPP_WEBSITE_ORIGIN", str(issues))
                self.assertNotIn(origin, str(issues))
                self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
        with self.settings(WHATSAPP_DEFAULT_LANGUAGE="unsupported"):
            self.assertIn(
                "WHATSAPP_DEFAULT_LANGUAGE", str(meta_configuration_checks(None))
            )
            self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
        self.http.assert_not_called()

    def test_production_requires_supported_shared_cache_that_reports_failures(self):
        with self.settings(
            PRODUCTION=True,
            DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}},
        ):
            for backend in (
                "django.core.cache.backends.redis.RedisCache",
                "django.core.cache.backends.memcached.PyMemcacheCache",
                "django.core.cache.backends.memcached.PyLibMCCache",
            ):
                with self.settings(CACHES={"default": {"BACKEND": backend}}):
                    self.assertEqual(meta_configuration_checks(None), [])
                with self.settings(
                    CACHES={
                        "default": {"BACKEND": backend, "OPTIONS": {"ignore_exc": True}}
                    }
                ):
                    self.assertIn(
                        "cache errors must not be ignored",
                        str(meta_configuration_checks(None)),
                    )
            with self.settings(CACHES={"default": {"BACKEND": "untrusted.RedisCache"}}):
                self.assertIn(
                    "shared Redis or Memcached required",
                    str(meta_configuration_checks(None)),
                )

    def test_consultation_template_has_only_the_existing_website_cta_suffix(self):
        for language in ("ar", "en"):
            for route in (
                "guest_consultation_detail",
                "patient_portal_consultation_detail",
            ):
                path = reverse(
                    route + ("_en" if language == "en" else ""), args=[uuid.uuid4()]
                )
                self.assertTrue(
                    meta.send_consultation_notification(
                        SYNTHETIC_PHONE,
                        REPLY_MESSAGES[language],
                        "https://clinic.example.test" + path,
                        language,
                    )
                )
                template = self.payload()["template"]
                self.assertEqual(template["name"], "synthetic_reply")
                self.assertEqual(
                    template["components"], [meta._url_button(path.lstrip("/"))]
                )
                self.assertNotIn(SYNTHETIC_PHONE, json.dumps(template))

    def test_consultation_content_and_untrusted_urls_are_rejected(self):
        valid = "https://clinic.example.test" + reverse(
            "guest_consultation_detail", args=[uuid.uuid4()]
        )
        self.assertFalse(
            meta.send_consultation_notification(
                SYNTHETIC_PHONE, "private-payload-sentinel", valid, "ar"
            )
        )
        for url in (
            "https://other.example.test/consult/",
            "https://clinic.example.test/records/",
            valid + "?private=sentinel",
            valid + "#sentinel",
            valid.replace("https:", "http:"),
            "https://clinic.example.test@other.example.test/",
            "https://clinic.example.test/book/",
        ):
            self.assertFalse(
                meta.send_consultation_notification(
                    SYNTHETIC_PHONE, REPLY_MESSAGES["ar"], url, "ar"
                )
            )
        self.http.assert_not_called()

    def test_appointment_payload_contains_only_date_and_time(self):
        starts_at = timezone.now() + timedelta(days=1)
        for kind, name in (
            ("BOOKING_CONFIRMATION", "synthetic_confirmation"),
            ("APPOINTMENT_REMINDER", "synthetic_reminder"),
        ):
            self.assertTrue(
                meta.send_appointment_notification(
                    SYNTHETIC_PHONE, kind, starts_at, "en"
                )
            )
            template = self.payload()["template"]
            self.assertEqual(template["name"], name)
            params = template["components"][0]["parameters"]
            self.assertEqual(
                params,
                [
                    {
                        "type": "text",
                        "text": timezone.localtime(starts_at).strftime("%Y-%m-%d"),
                    },
                    {
                        "type": "text",
                        "text": timezone.localtime(starts_at).strftime("%H:%M"),
                    },
                ],
            )

    def test_provider_failures_do_not_log_secrets_phones_or_payloads_or_retry(self):
        sentinel = "synthetic-access-token private-payload-sentinel " + SYNTHETIC_PHONE
        with self.assertLogs("apps.whatsapp.meta", level="WARNING") as logs:
            self.response.status = 400
            self.response.read.return_value = sentinel.encode()
            self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
            self.response.read.assert_not_called()
            self.connection.request.side_effect = TimeoutError(sentinel)
            self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
        self.assertEqual(self.connection.request.call_count, 2)
        for value in (
            "synthetic-access-token",
            "private-payload-sentinel",
            SYNTHETIC_PHONE,
            "123456",
            "Authorization",
        ):
            self.assertNotIn(value, " ".join(logs.output))

    def test_response_requires_bounded_parseable_acceptance(self):
        for body in (
            b"{}",
            b"[]",
            b'{"messages":[]}',
            b'{"messages":[{}]}',
            b"not-json",
            b"x" * 16385,
        ):
            with self.subTest(body_length=len(body)):
                self.response.read.return_value = body
                self.assertFalse(meta.send_guest_otp(SYNTHETIC_PHONE, "123456", "ar"))
        self.response.read.assert_called_with(16385)

    def test_webhook_access_logs_are_suppressed_without_affecting_other_routes(self):
        guard = WebhookPrivacyFilter()
        secret_record = logging.LogRecord(
            "django.server",
            20,
            "",
            0,
            '"GET %s HTTP/1.1" %s',
            ("/integrations/whatsapp/webhook/?hub.verify_token=synthetic-secret", 200),
            None,
        )
        self.assertFalse(guard.filter(secret_record))
        normal = logging.LogRecord(
            "django.server", 20, "", 0, '"GET /book/ HTTP/1.1" 200', (), None
        )
        self.assertTrue(guard.filter(normal))
