from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.clinic.models import Doctor
from apps.patients.models import Patient


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    PATIENT_OTP_TEMPORARY_MODE=False,
)
class VerifiedRegistrationPatientProfileTests(TestCase):
    phone = "+12025550141"
    password = "Synthetic-registration-password-741!"

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.sender = Mock(return_value=True)
        sender_override = override_settings(PATIENT_ACCOUNT_OTP_SENDER=self.sender)
        sender_override.enable()
        self.addCleanup(sender_override.disable)
        code_patch = patch(
            "apps.patients.account_otp.generate_otp_code",
            return_value="123456",
        )
        code_patch.start()
        self.addCleanup(code_patch.stop)

    def register_and_verify(self, *, full_name="Synthetic Verified Patient"):
        register_url = reverse("patient_portal_register_en")
        start = self.client.post(
            register_url,
            {
                "action": "start",
                "phone": self.phone,
                "full_name": full_name,
                "email": "verified-profile@example.test",
                "password1": self.password,
                "password2": self.password,
            },
        )
        self.assertEqual(start.status_code, 302)
        verify = self.client.post(
            register_url,
            {"action": "verify", "otp": "123456"},
        )
        self.assertEqual(verify.status_code, 302)
        return get_user_model().objects.get(username=self.phone)

    def test_verified_registration_creates_linked_patient_visible_to_staff(self):
        full_name = "Synthetic Verified Patient"
        user = self.register_and_verify(full_name=full_name)

        patient = Patient.objects.get(user=user)
        self.assertEqual(patient.full_name, full_name)
        self.assertEqual(patient.phone_e164, self.phone)

        Doctor.objects.create(
            full_name_ar="طبيب تجريبي",
            full_name_en="Synthetic Doctor",
            title_ar="د.",
            title_en="Dr.",
            is_active=True,
        )
        staff = get_user_model().objects.create_user(
            username="synthetic-profile-staff",
            password="Synthetic-staff-password-852!",
            is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("dashboard_patient_list"), {"lang": "en"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, full_name)

    def test_existing_unlinked_medical_record_is_not_silently_claimed_or_duplicated(self):
        existing = Patient.objects.create(
            full_name="Synthetic Existing Booking",
            phone_raw=self.phone,
            phone_e164=self.phone,
        )

        user = self.register_and_verify(full_name="Synthetic Portal Account")

        existing.refresh_from_db()
        self.assertIsNone(existing.user_id)
        self.assertFalse(Patient.objects.filter(user=user).exists())
        self.assertEqual(Patient.objects.filter(phone_e164=self.phone).count(), 1)
