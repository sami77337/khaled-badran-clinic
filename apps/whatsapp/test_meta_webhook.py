import hashlib
import hmac
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.whatsapp import views as whatsapp_views


@override_settings(
    WHATSAPP_META_APP_SECRET="webhook-test-key",
    WHATSAPP_META_VERIFY_TOKEN="verify-test-value",
    WHATSAPP_WEBSITE_ORIGIN="https://clinic.example.test",
    WHATSAPP_DEFAULT_LANGUAGE="ar",
)
class MetaWebhookTests(TestCase):
    phone = "962790000001"

    def setUp(self):
        cache.clear()
        self.url = reverse("whatsapp_meta_webhook")

    def _signature(self, raw):
        digest = hmac.new(b"webhook-test-key", raw, hashlib.sha256).hexdigest()
        return "sha256=" + digest

    def _payload(self, message):
        return {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"field": "messages", "value": {"messages": [message]}}]}],
        }

    def _post(self, message):
        raw = json.dumps(self._payload(message)).encode()
        return self.client.post(
            self.url,
            data=raw,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=self._signature(raw),
        )

    def test_get_verification_success_and_failure(self):
        ok = self.client.get(self.url, {"hub.mode": "subscribe", "hub.verify_token": "verify-test-value", "hub.challenge": "12345"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.content, b"12345")
        bad = self.client.get(self.url, {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"})
        self.assertEqual(bad.status_code, 403)

    @patch("apps.whatsapp.views.send_main_menu", return_value=True)
    def test_valid_signed_text_event_is_accepted(self, send_menu):
        response = self._post({"from": self.phone, "id": "wamid.test.1", "type": "text", "text": {"body": "hello"}})
        self.assertEqual(response.status_code, 200)
        send_menu.assert_called_once_with(self.phone, "ar")

    def test_missing_and_invalid_signatures_are_rejected(self):
        missing = self.client.post(self.url, data=b"{}", content_type="application/json")
        self.assertEqual(missing.status_code, 403)
        raw = json.dumps(self._payload({"id": "wamid.test.bad"})).encode()
        bad = self.client.post(self.url, data=raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=deadbeef")
        self.assertEqual(bad.status_code, 403)

    @patch("apps.whatsapp.views.send_main_menu", return_value=True)
    def test_duplicate_message_id_is_processed_once(self, send_menu):
        message = {"from": self.phone, "id": "wamid.test.duplicate", "type": "text", "text": {"body": "hello"}}
        self.assertEqual(self._post(message).status_code, 200)
        self.assertEqual(self._post(message).status_code, 200)
        self.assertEqual(send_menu.call_count, 1)

    @patch("apps.whatsapp.views.send_text", return_value=True)
    def test_staff_handoff_stops_automatic_reply_loop(self, send_text):
        whatsapp_views._route_interactive(self.phone, "kbc_staff", "ar")
        send_text.assert_called_once()
        with patch("apps.whatsapp.views.send_main_menu", return_value=True) as send_menu:
            response = self._post({"from": self.phone, "id": "wamid.test.staff", "type": "text", "text": {"body": "رسالة للعيادة"}})
        self.assertEqual(response.status_code, 200)
        send_menu.assert_not_called()

    @patch("apps.whatsapp.views.send_text", return_value=True)
    @patch("apps.whatsapp.views.send_main_menu", return_value=True)
    def test_menu_keyword_leaves_staff_handoff(self, send_menu, send_text):
        whatsapp_views._route_interactive(self.phone, "kbc_staff", "ar")
        response = self._post({"from": self.phone, "id": "wamid.test.menu", "type": "text", "text": {"body": "القائمة"}})
        self.assertEqual(response.status_code, 200)
        send_menu.assert_called_once_with(self.phone, "ar")

    @patch("apps.whatsapp.views.send_cta_url", return_value=True)
    def test_routes_use_named_cta_buttons(self, send_cta):
        expected = {
            "kbc_book": ("احجز موعدك", "/book/"),
            "kbc_consult_registered": ("ابدأ الاستشارة", "/portal/consultations/new/"),
            "kbc_consult_guest": ("ابدأ الاستشارة", "/consult/"),
            "kbc_portal": ("دخول حساب المريض", "/portal/login/"),
        }
        for reply_id, (label, suffix) in expected.items():
            send_cta.reset_mock()
            whatsapp_views._route_interactive(self.phone, reply_id, "ar")
            kwargs = send_cta.call_args.kwargs
            self.assertEqual(kwargs["label"], label)
            self.assertTrue(kwargs["url"].endswith(suffix))
            self.assertNotIn("https://", kwargs["body"])

        send_cta.reset_mock()
        whatsapp_views._route_interactive(self.phone, "kbc_location", "ar")
        kwargs = send_cta.call_args.kwargs
        self.assertEqual(kwargs["label"], "افتح الموقع على الخريطة")
        self.assertIn("google.com/maps", kwargs["url"])
