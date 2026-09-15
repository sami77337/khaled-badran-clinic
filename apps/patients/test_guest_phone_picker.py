from django.test import TestCase, override_settings
from django.urls import reverse

from apps.patients.transient_forms import GuestPhoneForm


@override_settings(PATIENT_OTP_TEMPORARY_MODE=True)
class GuestConsultationPhonePickerTests(TestCase):
    def test_guest_entry_reuses_shared_country_picker_in_arabic_and_english(self):
        for route_name in ("guest_consultation_entry", "guest_consultation_entry_en"):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(
                    response, "booking/partials/international_phone_field.html"
                )
                self.assertContains(response, "css/auth-phone.css")
                self.assertContains(response, "js/booking.js")
                self.assertContains(response, "data-booking-patient-form")
                self.assertContains(response, "data-booking-phone-control")
                self.assertContains(response, "data-booking-country-trigger")
                self.assertContains(response, "+962")

    def test_guest_phone_form_keeps_server_side_e164_normalization(self):
        form = GuestPhoneForm({"phone": "+12025550123"}, language="en")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["phone"], "+12025550123")
