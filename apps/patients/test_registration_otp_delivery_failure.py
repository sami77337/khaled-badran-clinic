"""Regression coverage for registration OTP delivery failures."""

from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import account_otp as otp
from .models import AccountOtpChallenge


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RegistrationOtpDeliveryFailureTests(TestCase):
    phone = "+12025550101"
    password = "Synthetic-account-password-781!"

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _data(self):
        return {
            "phone": self.phone,
            "full_name": "Synthetic Account",
            "email": "synthetic@example.test",
            "password1": self.password,
            "password2": self.password,
            "action": "start",
        }

    def test_failed_initial_send_returns_to_registration_without_fake_verify_stage(self):
        sender = Mock(side_effect=RuntimeError("private-provider-sentinel"))
        with override_settings(PATIENT_ACCOUNT_OTP_SENDER=sender), patch(
            "apps.patients.account_otp.generate_otp_code", return_value="123456"
        ):
            response = self.client.post(reverse("patient_portal_register_en"), self._data())

        self.assertRedirects(response, reverse("patient_portal_register_en"))
        follow = self.client.get(response.url)
        self.assertContains(
            follow,
            "Verification service is temporarily unavailable. Please try again later.",
        )
        self.assertNotContains(follow, "private-provider-sentinel")
        self.assertFalse(get_user_model().objects.exists())
        challenge = AccountOtpChallenge.objects.get()
        self.assertEqual(challenge.otp_digest, "")
        self.assertIn(otp.REGISTRATION_SESSION_KEY, self.client.session)

    def test_failed_resend_surfaces_unavailable_instead_of_claiming_code_was_sent(self):
        sender = Mock(return_value=True)
        with override_settings(PATIENT_ACCOUNT_OTP_SENDER=sender), patch(
            "apps.patients.account_otp.generate_otp_code", return_value="123456"
        ):
            start = self.client.post(reverse("patient_portal_register_en"), self._data())
        self.assertRedirects(start, reverse("patient_portal_register_en") + "?verify=1")

        cache.clear()
        challenge = AccountOtpChallenge.objects.get()
        challenge.last_sent_at = timezone.now() - timedelta(seconds=61)
        challenge.save(update_fields=["last_sent_at"])
        sender.side_effect = RuntimeError("private-provider-sentinel")
        with override_settings(PATIENT_ACCOUNT_OTP_SENDER=sender):
            response = self.client.post(
                reverse("patient_portal_register_en"),
                {"action": "resend"},
                follow=True,
            )

        self.assertContains(
            response,
            "Verification service is temporarily unavailable. Please try again later.",
        )
        self.assertNotContains(response, "private-provider-sentinel")
        challenge.refresh_from_db()
        self.assertEqual(challenge.otp_digest, "")
        self.assertFalse(get_user_model().objects.exists())
