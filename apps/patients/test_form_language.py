from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password, password_validators_help_text_html
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.html import escape

from apps.patients.models import AccountPhoneChangeChallenge, AppointmentLinkRecoveryChallenge, Consultation, Patient


class PageFormLanguageTests(TestCase):
    password = "Synthetic-locale-pass-392!"

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="+962790008801", password=cls.password)
        cls.staff = get_user_model().objects.create_user(username="synthetic-locale-staff", is_staff=True)
        cls.patient = Patient.objects.create(user=cls.user, full_name="Synthetic locale patient")
        cls.consultation = Consultation.objects.create(patient=cls.patient, question="Synthetic question")
        for model in (AccountPhoneChangeChallenge, AppointmentLinkRecoveryChallenge):
            model.objects.create(
                user=cls.user, phone_raw="+962790008802", phone_e164="+962790008802",
                otp_digest="synthetic-unused-digest", expires_at=timezone.now() + timedelta(minutes=5),
                last_sent_at=timezone.now(),
            )

    def post(self, route, language, data, *, cookie=False, staff=False):
        cache.clear()
        self.client.force_login(self.staff if staff else self.user)
        opposite = "ar" if language == "en" else "en"
        self.client.cookies.pop(settings.LANGUAGE_COOKIE_NAME, None)
        if cookie:
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = opposite
        if staff:
            url = reverse(route, kwargs={"public_id": self.consultation.public_id}) + f"?lang={language}"
        else:
            url = reverse(route + ("_en" if language == "en" else ""))
        response = self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=opposite)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(translation.get_language(), opposite, "page scope must restore the middleware locale")
        return response

    def assert_message_language(self, response, message, language):
        opposite = "ar" if language == "en" else "en"
        with translation.override(language):
            expected = translation.gettext(message)
        with translation.override(opposite):
            unexpected = translation.gettext(message)
        self.assertNotEqual(expected, unexpected)
        html = response.content.decode()
        self.assertTrue(escape(expected) in html, f"Missing {language} validation: {expected}")
        self.assertFalse(escape(unexpected) in html, f"Unexpected {opposite} validation: {unexpected}")

    def test_required_errors_follow_page_over_browser_and_cookie_locale(self):
        for language in ("ar", "en"):
            for cookie in (False, True):
                for route, data in (
                    ("patient_portal_link_appointment", {}),
                    ("patient_portal_consultation_new", {}),
                    ("patient_portal_password_change", {"action": "password"}),
                    ("patient_portal_password_change", {"action": "phone_start"}),
                    ("patient_portal_link_appointment_recovery", {"action": "start"}),
                ):
                    with self.subTest(language=language, cookie=cookie, route=route, data=data):
                        response = self.post(route, language, data, cookie=cookie)
                        self.assert_message_language(response, "This field is required.", language)

    def test_password_errors_and_construction_help_follow_page_language(self):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                with translation.override(language):
                    with self.assertRaises(ValidationError) as invalid:
                        validate_password("123", self.user)
                    expected_errors = list(invalid.exception.messages)
                    expected_help = str(password_validators_help_text_html())
                response = self.post("patient_portal_password_change", language, {
                    "old_password": self.password, "new_password1": "123", "new_password2": "123",
                })
                for message in expected_errors:
                    self.assertContains(response, escape(message))
                self.assertContains(response, expected_help)

    def test_phone_and_otp_invalid_errors_follow_page_language(self):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                response = self.post("patient_portal_password_change", language, {
                    "action": "phone_start", "current_password": self.password, "new_phone": "invalid",
                })
                self.assertContains(response, "أدخل رقم هاتف صالحًا." if language == "ar" else "Enter a valid phone number.")
                for route, action in (
                    ("patient_portal_password_change", "phone_verify"),
                    ("patient_portal_link_appointment_recovery", "verify"),
                ):
                    response = self.post(route, language, {
                        "action": action, "challenge_id": "invalid", "otp": "abcdef",
                    }, cookie=True)
                    if action == "verify":
                        expected = "رمز التحقق غير صالح أو منتهي." if language == "ar" else "The verification code is invalid or expired."
                        self.assertTrue(expected in response.content.decode(), "Existing recovery error must remain localized")
                        self.assertNotContains(response, 'value="abcdef"')
                    else:
                        self.assert_message_language(response, "Enter a valid value.", language)
                    self.assertEqual(response.context["verify_form"].errors.as_data()["challenge_id"][0].code, "invalid")

    def test_staff_reply_required_and_invalid_status_follow_selected_language(self):
        for language in ("ar", "en"):
            for cookie in (False, True):
                for data in ({}, {"status": "invalid", "staff_reply": "Synthetic reply"}):
                    with self.subTest(language=language, cookie=cookie, data=data):
                        response = self.post("dashboard_consultation_detail", language, data, cookie=cookie, staff=True)
                        if not data:
                            self.assert_message_language(response, "This field is required.", language)
                        else:
                            with translation.override(language):
                                expected = str(forms.ChoiceField.default_error_messages["invalid_choice"]) % {"value": "invalid"}
                            self.assertContains(response, escape(expected))
