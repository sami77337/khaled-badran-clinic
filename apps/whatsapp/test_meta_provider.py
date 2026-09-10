import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.whatsapp.meta import MAIN_MENU_COPY, consultation_menu_payload, main_menu_payload, send_consultation_notice, send_guest_otp
from apps.whatsapp.notifications import REPLY_MESSAGES


@override_settings(
    WHATSAPP_META_TEMPLATE_LANGUAGE_AR="ar",
    WHATSAPP_META_TEMPLATE_LANGUAGE_EN="en_US",
    WHATSAPP_META_TEMPLATE_GUEST_OTP="guest_otp_test",
    WHATSAPP_META_TEMPLATE_CONSULTATION_REPLY="consult_reply_test",
    WHATSAPP_WEBSITE_ORIGIN="https://clinic.example.test",
)
class MetaPayloadTests(SimpleTestCase):
    phone = "+962790000001"

    def test_main_menu_stable_ids(self):
        payload = main_menu_payload(self.phone, "ar")
        rows = payload["interactive"]["action"]["sections"][0]["rows"]
        self.assertEqual([row["id"] for row in rows], ["kbc_book", "kbc_consult", "kbc_portal", "kbc_location", "kbc_staff"])
        self.assertEqual(rows[0]["title"], "حجز موعد")
        self.assertEqual(rows[-1]["title"], "التحدث مع العيادة")

    def test_consultation_submenu_stable_ids(self):
        payload = consultation_menu_payload(self.phone, "ar")
        buttons = payload["interactive"]["action"]["buttons"]
        self.assertEqual([button["reply"]["id"] for button in buttons], ["kbc_consult_registered", "kbc_consult_guest"])

    @patch("apps.whatsapp.meta._post", return_value=True)
    def test_guest_otp_payload(self, post):
        self.assertTrue(send_guest_otp(self.phone, "123456", "ar"))
        payload = post.call_args.args[0]
        self.assertEqual(payload["template"]["name"], "guest_otp_test")
        components = payload["template"]["components"]
        self.assertEqual(components[0]["parameters"][0]["text"], "123456")
        self.assertEqual(components[1]["parameters"][0]["text"], "123456")

    @patch("apps.whatsapp.meta._post", return_value=True)
    def test_consultation_notice_excludes_reply_text(self, post):
        reply_text = "Private consultation reply"
        url = "https://clinic.example.test/consult/00000000-0000-0000-0000-000000000001/"
        self.assertTrue(send_consultation_notice(self.phone, reply_text, url, "ar"))
        serialized = json.dumps(post.call_args.args[0], ensure_ascii=False)
        self.assertNotIn(reply_text, serialized)
        self.assertIn("consult/00000000-0000-0000-0000-000000000001/", serialized)

    def test_patient_copy_omits_rejected_wording(self):
        copy = " ".join(REPLY_MESSAGES.values()) + " " + " ".join(item["body"] for item in MAIN_MENU_COPY.values())
        lowered = copy.casefold()
        for forbidden in ("آمن", "آمنة", "الأمان", "secure", "security"):
            self.assertNotIn(forbidden.casefold(), lowered)
