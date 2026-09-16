from unittest.mock import call, patch

from django.test import SimpleTestCase, override_settings

from apps.patients.otp import (
    send_account_phone_change_otp,
    send_appointment_link_recovery_otp,
    send_patient_account_otp,
)
from apps.whatsapp.checks import meta_configuration_checks


OTP_META_SENDER = "apps.whatsapp.meta.send_guest_otp"
SYNTHETIC_PHONE = "+12025550101"

META_SETTINGS = {
    "WHATSAPP_META_ENABLED": True,
    "WHATSAPP_META_ACCESS_TOKEN": "synthetic-access-token",
    "WHATSAPP_META_APP_SECRET": "synthetic-app-secret",
    "WHATSAPP_META_VERIFY_TOKEN": "synthetic-verify-token",
    "WHATSAPP_META_PHONE_NUMBER_ID": "101",
    "WHATSAPP_META_WABA_ID": "202",
    "WHATSAPP_META_GRAPH_VERSION": "v999.0",
    "WHATSAPP_WEBSITE_ORIGIN": "https://clinic.example.test",
    "WHATSAPP_META_OTP_TEMPLATE": "synthetic_otp",
    "WHATSAPP_META_CONSULTATION_REPLY_TEMPLATE": "synthetic_reply",
    "WHATSAPP_META_BOOKING_CONFIRMATION_TEMPLATE": "synthetic_confirmation",
    "WHATSAPP_META_APPOINTMENT_REMINDER_TEMPLATE": "synthetic_reminder",
    "WHATSAPP_META_TEMPLATE_LANGUAGE_AR": "ar",
    "WHATSAPP_META_TEMPLATE_LANGUAGE_EN": "en_US",
    "WHATSAPP_DEFAULT_LANGUAGE": "ar",
    "GUEST_CONSULTATION_OTP_SENDER": OTP_META_SENDER,
    "PATIENT_ACCOUNT_OTP_SENDER": OTP_META_SENDER,
    "ACCOUNT_PHONE_CHANGE_OTP_SENDER": OTP_META_SENDER,
    "APPOINTMENT_LINK_RECOVERY_OTP_SENDER": OTP_META_SENDER,
    "WHATSAPP_CONSULTATION_NOTIFICATION_SENDER": "apps.whatsapp.meta.send_consultation_notification",
}


@override_settings(**META_SETTINGS)
class OtpCloseoutTests(SimpleTestCase):
    def test_configuration_check_requires_every_patient_otp_sender(self):
        self.assertEqual(meta_configuration_checks(None), [])
        for setting_name in (
            "GUEST_CONSULTATION_OTP_SENDER",
            "PATIENT_ACCOUNT_OTP_SENDER",
            "ACCOUNT_PHONE_CHANGE_OTP_SENDER",
            "APPOINTMENT_LINK_RECOVERY_OTP_SENDER",
        ):
            with self.subTest(setting_name=setting_name), self.settings(
                **{setting_name: ""}
            ):
                issues = meta_configuration_checks(None)
                self.assertEqual(len(issues), 1)
                self.assertEqual(issues[0].id, "whatsapp.E001")
                self.assertIn(setting_name, issues[0].hint)

    @patch("apps.whatsapp.meta.send_guest_otp", return_value=True)
    def test_account_phone_and_link_flows_share_approved_meta_otp_sender(self, sender):
        send_patient_account_otp(SYNTHETIC_PHONE, "123456", "ar")
        send_account_phone_change_otp(SYNTHETIC_PHONE, "234567", "en")
        send_appointment_link_recovery_otp(SYNTHETIC_PHONE, "345678", "ar")

        self.assertEqual(
            sender.call_args_list,
            [
                call(SYNTHETIC_PHONE, "123456", "ar"),
                call(SYNTHETIC_PHONE, "234567", "en"),
                call(SYNTHETIC_PHONE, "345678", "ar"),
            ],
        )
