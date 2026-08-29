
from datetime import datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog
from apps.patients.forms import (
    GENERIC_LINK_ERROR,
    GENERIC_LOGIN_ERROR,
    GENERIC_REGISTRATION_ERROR,
    PatientRegistrationForm,
    auth_error_message,
)
from apps.patients import rate_limits
from apps.records.models import ClinicalNote, PublicCase, RecordMedia, VisitRecord
from .models import Patient


TEST_PASSWORD = "PortalPass123!Strong"
NEW_TEST_PASSWORD = "NewPortalPass123!Strong"


class PatientModelTests(TestCase):
    def test_patient_stores_raw_and_normalized_phone_placeholders(self):
        patient = Patient.objects.create(
            full_name="Test Patient",
            phone_raw="0790000000",
            phone_e164="+962790000000",
            whatsapp_phone_raw="0790000000",
            whatsapp_phone_e164="+962790000000",
        )

        self.assertEqual(patient.phone_raw, "0790000000")
        self.assertEqual(patient.phone_e164, "+962790000000")
        self.assertEqual(patient.whatsapp_phone_raw, "0790000000")
        self.assertEqual(patient.whatsapp_phone_e164, "+962790000000")

    def test_patient_user_link_is_optional(self):
        patient = Patient.objects.create(
            full_name="Optional Account Patient",
            phone_raw="0791111111",
            phone_e164="+962791111111",
        )

        self.assertIsNone(patient.user)


class PatientPortalTestMixin:
    def create_user(self, username="+962791234567", password=TEST_PASSWORD, **kwargs):
        defaults = {
            "email": "portal@example.test",
            "first_name": "Portal Patient",
        }
        defaults.update(kwargs)
        return get_user_model().objects.create_user(
            username=username,
            password=password,
            **defaults,
        )

    def create_doctor(self):
        return Doctor.objects.create(
            full_name_ar="خالد حسان بدران",
            full_name_en="Khaled Hassan Badran",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="استشاري الأنف والأذن والحنجرة",
            specialty_en="ENT consultant",
            is_active=True,
        )

    def create_visit_type(self, doctor=None):
        return VisitType.objects.create(
            doctor=doctor or self.create_doctor(),
            name_ar="كشف جديد",
            name_en="New consultation",
            duration_minutes=30,
            is_active=True,
        )

    def create_patient(self, *, user=None, full_name="Test Patient", phone_raw="0791234567", phone_e164="+962791234567"):
        return Patient.objects.create(
            user=user,
            full_name=full_name,
            phone_raw=phone_raw,
            phone_e164=phone_e164,
        )

    def aware_at(self, *, days=1, hour=9, minute=0):
        day = timezone.localdate() + timedelta(days=days)
        return timezone.make_aware(
            datetime.combine(day, time(hour, minute)),
            timezone.get_current_timezone(),
        )

    def create_appointment(self, *, patient=None, user=None, days=1, status=Appointment.Status.CONFIRMED):
        doctor = self.create_doctor()
        visit_type = self.create_visit_type(doctor=doctor)
        patient = patient or self.create_patient(user=user)
        starts_at = self.aware_at(days=days)
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=visit_type.duration_minutes),
            status=status,
            booking_note="Private booking note.",
        )

    def assert_no_cache(self, response):
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)

    def assert_form_errors_hide_database_details(self, form):
        rendered_errors = " ".join(
            message
            for error_list in form.errors.values()
            for message in error_list
        ).lower()
        for marker in (
            "sql syntax",
            "auth_user",
            "integrityerror",
            "databaseerror",
            "sqlite",
            "postgres",
            "mysql",
            "traceback",
            "select ",
            "insert ",
            "delete from",
            "drop table",
        ):
            with self.subTest(database_detail=marker):
                self.assertNotIn(marker, rendered_errors)


class PatientPortalAuthenticationTests(PatientPortalTestMixin, TestCase):
    def test_canonical_login_routes_render_with_natural_language_direction(self):
        arabic = self.client.get(reverse("login"))
        english = self.client.get(reverse("login_en"))

        self.assertEqual(arabic.status_code, 200)
        self.assertEqual(english.status_code, 200)
        self.assertContains(arabic, '<html lang="ar" dir="rtl">')
        self.assertContains(english, '<html lang="en" dir="ltr">')
        self.assertNotContains(arabic, '<footer class="site-footer">')
        self.assertNotContains(english, '<footer class="site-footer">')

    def test_patient_is_default_and_role_selector_is_accessible_and_no_js_safe(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.context["selected_role"], "patient")
        self.assertContains(response, 'data-selected-role="patient"')
        self.assertContains(response, 'data-auth-role="patient"')
        self.assertContains(response, 'data-auth-role="doctor"')
        self.assertContains(response, 'aria-selected="true"')
        self.assertContains(response, f'href="{reverse("login")}?role=doctor"')
        self.assertContains(response, 'role="tablist"')
        self.assertContains(response, 'role="tabpanel"')

    def test_login_includes_role_switching_and_phone_composition_javascript_hooks(self):
        response = self.client.get(reverse("login"))
        javascript = (settings.BASE_DIR / "static" / "js" / "auth-login.js").read_text(encoding="utf-8")

        self.assertContains(response, f'src="{settings.STATIC_URL}js/auth-login.js"')
        self.assertContains(response, "data-auth-role-tabs")
        self.assertContains(response, "data-patient-login-form")
        self.assertIn('event.preventDefault()', javascript)
        self.assertIn('aria-selected', javascript)
        self.assertIn('preventScroll: true', javascript)
        self.assertIn('addEventListener("formdata"', javascript)

    def test_login_phone_ui_keeps_placeholder_and_selector_without_formatting_helper(self):
        response = self.client.get(reverse("login_en"))

        self.assertContains(response, ">+962</span>")
        self.assertContains(response, 'placeholder="7XXXXXXXX"')
        self.assertNotContains(response, "Formatting example: 7XXXXXXXX")
        self.assertNotContains(response, "data-booking-phone-hint")
        self.assertNotContains(response, "79XXXXXXX")
        self.assertNotContains(response, "07XXXXXXXX")

    def test_unified_login_omits_owner_removed_visual_copy_in_both_languages(self):
        arabic = self.client.get(reverse("login"))
        english = self.client.get(reverse("login_en"))
        stylesheet = (settings.BASE_DIR / "static" / "css" / "auth.css").read_text(encoding="utf-8")

        for response in (arabic, english):
            self.assertNotContains(response, "auth-secure-badge")
            self.assertNotContains(response, "auth-privacy-note")
            self.assertNotContains(response, "data-booking-example-label")
            self.assertNotContains(response, "data-booking-phone-hint")

        for removed_copy in (
            "دخول آمن ومشفّر",
            "سجّل الدخول للوصول إلى حسابك بأمان",
            "مثال للتنسيق: 7XXXXXXXX",
            "بياناتك محمية وفق ضوابط الخصوصية والأمان في العيادة.",
        ):
            self.assertNotContains(arabic, removed_copy)

        for removed_copy in (
            "Secure, encrypted access",
            "Sign in to securely access your account",
            "Formatting example: 7XXXXXXXX",
            "Your information is protected by the clinic’s privacy and security controls.",
        ):
            self.assertNotContains(english, removed_copy)

        self.assertNotIn(".auth-secure-badge", stylesheet)
        self.assertNotIn(".auth-privacy-note", stylesheet)
        self.assertIn("--auth-burgundy: #4A0F14;", stylesheet)
        self.assertIn("--auth-wood: #8B5A2B;", stylesheet)

    def test_registration_routes_use_the_approved_auth_shell_in_both_languages(self):
        route_cases = [
            ("patient_portal_register", "ar", "rtl", "إنشاء حساب", "login"),
            ("patient_portal_register_en", "en", "ltr", "Create your account", "login_en"),
        ]

        for route_name, language, direction, heading, login_route in route_cases:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "auth/base.html")
                self.assertTemplateNotUsed(response, "base.html")
                self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
                self.assertContains(response, 'class="auth-shell page-register')
                self.assertContains(response, 'class="auth-card auth-register-card"')
                self.assertContains(response, f'<h1 id="auth-title">{heading}</h1>')
                self.assertContains(response, f'href="{reverse(login_route)}"')
                self.assertContains(response, f'src="{settings.STATIC_URL}js/auth-login.js"')
                self.assertNotContains(response, '<footer class="site-footer">')
                self.assertNotContains(response, "data-mobile-booking-cta")
                self.assertNotContains(response, 'class="page-hero"')
                self.assertNotContains(response, 'class="container booking-layout"')

    def test_registration_preserves_the_exact_field_contract_and_accessible_controls(self):
        response = self.client.get(reverse("patient_portal_register_en"))
        form = response.context["form"]

        self.assertEqual(
            list(form.fields),
            ["full_name", "phone", "email", "password1", "password2"],
        )
        self.assertFalse(form.fields["email"].required)
        self.assertEqual(form.fields["email"].label, "Email (optional)")
        self.assertContains(response, 'name="full_name"', count=1)
        self.assertContains(response, 'autocomplete="name"', count=1)
        self.assertContains(response, 'name="phone"', count=1)
        self.assertContains(response, 'name="email"', count=1)
        self.assertContains(response, 'type="email"', count=1)
        self.assertContains(response, 'autocomplete="email"', count=1)
        self.assertContains(response, 'name="password1"', count=1)
        self.assertContains(response, 'name="password2"', count=1)
        self.assertContains(response, 'autocomplete="new-password"', count=2)
        self.assertContains(response, "data-password-toggle", count=2)
        self.assertContains(response, 'name="csrfmiddlewaretoken"', count=1)
        self.assertNotContains(response, 'name="first_name"')
        self.assertNotContains(response, 'name="last_name"')

    def test_registration_reuses_the_full_searchable_international_phone_selector(self):
        response = self.client.get(reverse("patient_portal_register_en"))
        javascript = (settings.BASE_DIR / "static" / "js" / "auth-login.js").read_text(encoding="utf-8")

        self.assertContains(response, ">+962</span>")
        self.assertContains(response, 'placeholder="7XXXXXXXX"')
        self.assertNotContains(response, "07XXXXXXXX")
        self.assertNotContains(response, "79XXXXXXX")
        self.assertContains(response, "data-booking-phone-control")
        self.assertContains(response, "data-booking-country-trigger")
        self.assertContains(response, "data-booking-country-search")
        self.assertContains(response, "data-booking-country-options")
        self.assertContains(
            response,
            'role="option"',
            count=len(response.context["phone_countries"]),
        )
        self.assertContains(response, "data-patient-register-form")
        self.assertNotContains(response, "data-booking-phone-hint")
        self.assertIn("[data-patient-register-form]", javascript)
        self.assertIn('addEventListener("formdata"', javascript)
        self.assertIn("event.formData.set", javascript)

    def test_registration_omits_legacy_copy_and_keeps_the_auth_visual_contract(self):
        arabic = self.client.get(reverse("patient_portal_register"))
        english = self.client.get(reverse("patient_portal_register_en"))
        stylesheet = (settings.BASE_DIR / "static" / "css" / "auth.css").read_text(encoding="utf-8")

        for removed_copy in (
            "حساب اختياري",
            "الموقع وواتساب غير مخصصين للطوارئ. في الحالات الطارئة اتصل بخدمات الطوارئ المحلية فوراً.",
            "بعد إنشاء الحساب، اربط موعدك باستخدام رمز التأكيد",
        ):
            self.assertNotContains(arabic, removed_copy)

        for removed_copy in (
            "Optional Account",
            "This website and WhatsApp are not for emergencies.",
            "After creating an account, link your appointment",
            "Account recovery",
        ):
            self.assertNotContains(english, removed_copy)

        self.assertNotContains(arabic, "trust-note")
        self.assertNotContains(english, "trust-note")
        self.assertIn("--auth-burgundy: #4A0F14;", stylesheet)
        self.assertIn("--auth-wood: #8B5A2B;", stylesheet)
        self.assertIn(".auth-register-page", stylesheet)
        self.assertIn("align-items: start;", stylesheet)

    def test_registration_form_keeps_phone_normalization_and_django_password_validation(self):
        composed_phone_form = PatientRegistrationForm(
            {
                "full_name": "Portal Patient",
                "phone": "+962791234568",
                "email": "",
                "password1": TEST_PASSWORD,
                "password2": TEST_PASSWORD,
            },
            language="en",
        )

        self.assertTrue(composed_phone_form.is_valid(), composed_phone_form.errors.as_json())
        self.assertEqual(composed_phone_form.normalized_phone, "+962791234568")

        weak_password_form = PatientRegistrationForm(
            {
                "full_name": "Portal Patient",
                "phone": "+962791234569",
                "email": "",
                "password1": "short",
                "password2": "short",
            },
            language="en",
        )

        self.assertFalse(weak_password_form.is_valid())
        self.assertIn("password1", weak_password_form.errors)
        self.assertNotIn("__all__", weak_password_form.errors)
        self.assertIn("too short", weak_password_form.errors["password1"][0])
        self.assertEqual(
            weak_password_form.errors.as_data()["password1"][0].code,
            "password_too_short",
        )

        arabic_weak_password_form = PatientRegistrationForm(
            {
                "full_name": "مريض البوابة",
                "phone": "+962791234570",
                "email": "",
                "password1": "short",
                "password2": "short",
            },
            language="ar",
        )

        self.assertFalse(arabic_weak_password_form.is_valid())
        self.assertEqual(
            list(arabic_weak_password_form.errors["password1"]),
            ["كلمة المرور قصيرة جدًا. يجب أن تتكون من 8 أحرف على الأقل."],
        )
        self.assertNotIn("__all__", arabic_weak_password_form.errors)
        self.assertEqual(
            arabic_weak_password_form.errors.as_data()["password1"][0].code,
            "password_too_short",
        )

    def test_registration_required_and_invalid_field_errors_are_localized(self):
        cases = (
            (
                "patient_portal_register",
                "10.20.0.1",
                {
                    "full_name": "الاسم الكامل مطلوب.",
                    "phone": "أدخل رقم هاتف صالحًا.",
                    "email": "أدخل بريدًا إلكترونيًا صالحًا.",
                    "password1": "كلمة المرور مطلوبة.",
                    "password2": "تأكيد كلمة المرور مطلوب.",
                },
            ),
            (
                "patient_portal_register_en",
                "10.20.0.2",
                {
                    "full_name": "Full name is required.",
                    "phone": "Enter a valid phone number.",
                    "email": "Enter a valid email address.",
                    "password1": "Password is required.",
                    "password2": "Password confirmation is required.",
                },
            ),
        )

        for route_name, remote_addr, expected_errors in cases:
            with self.subTest(route=route_name):
                response = self.client.post(
                    reverse(route_name),
                    {
                        "full_name": "",
                        "phone": "' OR 1=1 --",
                        "email": "not-an-email",
                        "password1": "",
                        "password2": "",
                    },
                    REMOTE_ADDR=remote_addr,
                )

                self.assertEqual(response.status_code, 200)
                form = response.context["form"]
                self.assertNotIn("__all__", form.errors)
                for field_name, expected_message in expected_errors.items():
                    with self.subTest(route=route_name, field=field_name):
                        self.assertEqual(list(form.errors[field_name]), [expected_message])
                        self.assertContains(response, expected_message)

    def test_registration_password_mismatch_is_localized_beside_confirmation(self):
        cases = (
            ("patient_portal_register", "ar", "كلمتا المرور غير متطابقتين.", "10.20.0.3"),
            ("patient_portal_register_en", "en", "Passwords do not match.", "10.20.0.4"),
        )

        for route_name, language, expected_message, remote_addr in cases:
            with self.subTest(language=language):
                response = self.client.post(
                    reverse(route_name),
                    {
                        "full_name": "Portal Patient",
                        "phone": "+962791234580",
                        "email": "",
                        "password1": TEST_PASSWORD,
                        "password2": NEW_TEST_PASSWORD,
                    },
                    REMOTE_ADDR=remote_addr,
                )

                self.assertEqual(response.status_code, 200)
                form = response.context["form"]
                self.assertEqual(list(form.errors["password2"]), [expected_message])
                self.assertEqual(
                    form.errors.as_data()["password2"][0].code,
                    "password_mismatch",
                )
                self.assertNotIn("__all__", form.errors)
                self.assertContains(response, expected_message)

    def test_canonical_patient_login_preserves_phone_normalization(self):
        self.create_user()

        response = self.client.post(
            reverse("login"),
            {
                "role": "patient",
                "phone": "0791234567",
                "password": TEST_PASSWORD,
            },
        )

        self.assertRedirects(response, reverse("patient_portal_dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(get_user_model().objects.get().pk))

    def test_patient_login_preserves_safe_next_and_rejects_external_next(self):
        user = self.create_user()
        safe_destination = reverse("patient_portal_account")

        safe_response = self.client.post(
            reverse("login"),
            {
                "role": "patient",
                "phone": "0791234567",
                "password": TEST_PASSWORD,
                "next": safe_destination,
            },
        )
        self.assertRedirects(safe_response, safe_destination, fetch_redirect_response=False)

        self.client.logout()
        external_response = self.client.post(
            reverse("login"),
            {
                "role": "patient",
                "phone": "+962791234567",
                "password": TEST_PASSWORD,
                "next": "https://attacker.example/private",
            },
        )
        self.assertRedirects(
            external_response,
            reverse("patient_portal_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_patient_login_failure_is_generic_and_never_reflects_password(self):
        self.create_user()
        submitted_password = "synthetic-secret-that-must-not-render"

        response = self.client.post(
            reverse("login"),
            {
                "role": "patient",
                "phone": "0791234567",
                "password": submitted_password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, auth_error_message("login_generic", "ar"))
        self.assertNotContains(response, submitted_password)

    def test_login_page_does_not_expose_existing_patient_information(self):
        user = self.create_user()
        self.create_patient(
            user=user,
            full_name="Synthetic Private Login Patient",
            phone_raw="0799999999",
            phone_e164="+962799999999",
        )

        response = self.client.get(reverse("login"))

        self.assertNotContains(response, "Synthetic Private Login Patient")
        self.assertNotContains(response, "0799999999")
        self.assertNotContains(response, "+962799999999")

    def test_valid_staff_user_can_login_in_doctor_mode(self):
        staff = self.create_user(username="clinic-doctor", is_staff=True)

        response = self.client.post(
            reverse("login_en"),
            {
                "role": "doctor",
                "username": "clinic-doctor",
                "password": TEST_PASSWORD,
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('dashboard_home')}?lang=en",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.client.session["_auth_user_id"], str(staff.pk))

    def test_arabic_doctor_login_defaults_to_dashboard_home(self):
        self.create_user(username="arabic-clinic-doctor", is_staff=True)

        response = self.client.post(
            reverse("login"),
            {
                "role": "doctor",
                "username": "arabic-clinic-doctor",
                "password": TEST_PASSWORD,
            },
        )

        self.assertRedirects(response, reverse("dashboard_home"), fetch_redirect_response=False)

    def test_doctor_login_preserves_valid_safe_next(self):
        self.create_user(username="next-clinic-doctor", is_staff=True)
        destination = reverse("staff_appointment_list")

        response = self.client.post(
            reverse("login_en"),
            {
                "role": "doctor",
                "username": "next-clinic-doctor",
                "password": TEST_PASSWORD,
                "next": destination,
            },
        )

        self.assertRedirects(response, destination, fetch_redirect_response=False)

    def test_doctor_login_rejects_external_next(self):
        self.create_user(username="safe-clinic-doctor", is_staff=True)

        response = self.client.post(
            reverse("login"),
            {
                "role": "doctor",
                "username": "safe-clinic-doctor",
                "password": TEST_PASSWORD,
                "next": "https://attacker.example/staff",
            },
        )

        self.assertRedirects(response, reverse("dashboard_home"), fetch_redirect_response=False)

    def test_valid_non_staff_user_cannot_login_in_doctor_mode(self):
        self.create_user(username="patient-not-staff")

        response = self.client.post(
            reverse("login"),
            {
                "role": "doctor",
                "username": "patient-not-staff",
                "password": TEST_PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, auth_error_message("login_generic", "ar"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_doctor_credentials_fail_generically_without_username_disclosure(self):
        submitted_password = "wrong-staff-secret"

        response = self.client.post(
            reverse("login"),
            {
                "role": "doctor",
                "username": "missing-clinic-user",
                "password": submitted_password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, auth_error_message("login_generic", "ar"))
        self.assertNotContains(response, submitted_password)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_authenticated_login_redirect_uses_real_authorization_not_requested_role(self):
        patient = self.create_user()
        self.client.force_login(patient)
        patient_response = self.client.get(reverse("login"), {"role": "doctor"})
        self.assertRedirects(
            patient_response,
            reverse("patient_portal_dashboard"),
            fetch_redirect_response=False,
        )

        self.client.logout()
        staff = self.create_user(username="authenticated-staff", is_staff=True)
        self.client.force_login(staff)
        staff_response = self.client.get(reverse("login_en"), {"role": "patient"})
        self.assertRedirects(
            staff_response,
            f"{reverse('dashboard_home')}?lang=en",
            fetch_redirect_response=False,
        )

    def test_legacy_login_urls_render_same_view_and_keep_post_compatibility(self):
        self.create_user()

        arabic_get = self.client.get(reverse("patient_portal_login"))
        english_get = self.client.get(reverse("patient_portal_login_en"))
        post_response = self.client.post(
            reverse("patient_portal_login"),
            {
                "role": "patient",
                "phone": "0791234567",
                "password": TEST_PASSWORD,
            },
        )

        self.assertEqual(arabic_get.status_code, 200)
        self.assertEqual(english_get.status_code, 200)
        self.assertContains(arabic_get, f'<link rel="canonical" href="http://testserver{reverse("login")}">')
        self.assertContains(
            english_get,
            f'<link rel="canonical" href="http://testserver{reverse("login_en")}">',
        )
        self.assertRedirects(post_response, reverse("patient_portal_dashboard"), fetch_redirect_response=False)

    def test_patient_protected_route_redirects_to_canonical_role_aware_login(self):
        destination = reverse("patient_portal_dashboard_en")

        response = self.client.get(destination)
        redirect = urlsplit(response["Location"])
        query = parse_qs(redirect.query)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(redirect.path, reverse("login_en"))
        self.assertEqual(query["role"], ["patient"])
        self.assertEqual(query["next"], [destination])

    def test_canonical_login_has_csrf_and_enforces_it(self):
        page = self.client.get(reverse("login"))
        csrf_client = Client(enforce_csrf_checks=True)
        post = csrf_client.post(
            reverse("login"),
            {"role": "patient", "phone": "0791234567", "password": TEST_PASSWORD},
        )

        self.assertContains(page, 'name="csrfmiddlewaretoken"', count=2)
        self.assertEqual(post.status_code, 403)

    def test_django_admin_login_remains_available(self):
        response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)

    def test_anonymous_dashboard_redirects_to_portal_login(self):
        response = self.client.get(reverse("patient_portal_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_anonymous_appointment_detail_redirects_to_portal_login(self):
        appointment = self.create_appointment()

        response = self.client.get(
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_registration_creates_user_with_hashed_password_and_logs_in(self):
        response = self.client.post(
            reverse("patient_portal_register"),
            {
                "full_name": "Portal Patient",
                "phone": "0791234567",
                "email": "patient@example.test",
                "password1": TEST_PASSWORD,
                "password2": TEST_PASSWORD,
            },
        )

        self.assertRedirects(response, reverse("patient_portal_dashboard"), fetch_redirect_response=False)
        user = get_user_model().objects.get(username="+962791234567")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertTrue(user.check_password(TEST_PASSWORD))
        self.assertNotEqual(user.password, TEST_PASSWORD)
        self.assertEqual(user.email, "patient@example.test")
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_registration_preserves_safe_next_and_rejects_external_next(self):
        safe_destination = reverse("patient_portal_account")

        safe_response = self.client.post(
            reverse("patient_portal_register"),
            {
                "full_name": "Safe Next Patient",
                "phone": "+962791234568",
                "email": "",
                "password1": TEST_PASSWORD,
                "password2": TEST_PASSWORD,
                "next": safe_destination,
            },
        )
        self.assertRedirects(safe_response, safe_destination, fetch_redirect_response=False)

        self.client.logout()
        external_response = self.client.post(
            reverse("patient_portal_register"),
            {
                "full_name": "External Next Patient",
                "phone": "+962791234569",
                "email": "",
                "password1": TEST_PASSWORD,
                "password2": TEST_PASSWORD,
                "next": "https://attacker.example/private",
            },
        )
        self.assertRedirects(
            external_response,
            reverse("patient_portal_dashboard"),
            fetch_redirect_response=False,
        )

    def test_registration_errors_are_inline_and_never_reflect_passwords(self):
        submitted_password = "SyntheticSecret123!DoNotReflect"

        response = self.client.post(
            reverse("patient_portal_register_en"),
            {
                "full_name": "",
                "phone": "+962791234570",
                "email": "not-an-email",
                "password1": submitted_password,
                "password2": "different-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-field has-error")
        self.assertContains(response, "auth-field-errors")
        self.assertContains(response, 'role="alert"')
        self.assertNotContains(response, submitted_password)
        self.assertNotContains(response, "different-password")

    def test_duplicate_phone_registration_uses_localized_non_enumerating_error(self):
        self.create_user()

        cases = (
            ("patient_portal_register", "ar", "10.20.0.5"),
            ("patient_portal_register_en", "en", "10.20.0.6"),
        )
        for route_name, language, remote_addr in cases:
            with self.subTest(language=language):
                response = self.client.post(
                    reverse(route_name),
                    {
                        "full_name": "Portal Patient",
                        "phone": "0791234567",
                        "email": "patient@example.test",
                        "password1": TEST_PASSWORD,
                        "password2": TEST_PASSWORD,
                    },
                    REMOTE_ADDR=remote_addr,
                )

                expected_message = auth_error_message("registration_generic", language)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    list(response.context["form"].non_field_errors()),
                    [expected_message],
                )
                self.assertContains(response, expected_message)
                self.assertContains(response, "auth-form-errors")
                self.assertNotContains(response, "This phone number already has an account.")
                self.assertNotContains(response, "+962791234567")
                self.assertNotContains(response, TEST_PASSWORD)
                self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_registration_create_race_uses_the_same_controlled_generic_error(self):
        form = PatientRegistrationForm(
            {
                "full_name": "Race-safe Patient",
                "phone": "+962791234581",
                "email": "race@example.test",
                "password1": TEST_PASSWORD,
                "password2": TEST_PASSWORD,
            },
            language="en",
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

        existing = self.create_user(username="+962791234581")
        existing_password_hash = existing.password
        created_user = form.save()

        self.assertIsNone(created_user)
        self.assertEqual(list(form.non_field_errors()), [GENERIC_REGISTRATION_ERROR])
        self.assert_form_errors_hide_database_details(form)
        self.assertEqual(get_user_model().objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.password, existing_password_hash)

    def test_registration_sql_like_values_cannot_bypass_duplicate_lookup(self):
        cases = (
            ("'; DROP TABLE auth_user; --", "+962791234582", "admin'--@example.test"),
            ("' OR 1=1 --", "+962791234583", "sql.payload@example.test"),
            ('" OR "1"="1', "+962791234584", "quoted.payload@example.test"),
        )
        existing_users = [
            self.create_user(username=phone, email=f"existing{index}@example.test")
            for index, (_, phone, _) in enumerate(cases)
        ]
        original_state = {
            user.pk: (user.username, user.email, user.password, user.is_staff)
            for user in existing_users
        }

        for index, (full_name, phone, email) in enumerate(cases):
            with self.subTest(full_name=full_name, email=email):
                response = self.client.post(
                    reverse("patient_portal_register_en"),
                    {
                        "full_name": full_name,
                        "phone": phone,
                        "email": email,
                        "password1": TEST_PASSWORD,
                        "password2": TEST_PASSWORD,
                    },
                    REMOTE_ADDR=f"10.21.0.{index + 1}",
                )

                self.assertEqual(response.status_code, 200)
                form = response.context["form"]
                self.assertNotIn("full_name", form.errors)
                self.assertNotIn("email", form.errors)
                self.assertEqual(
                    list(form.non_field_errors()),
                    [GENERIC_REGISTRATION_ERROR],
                )
                self.assert_form_errors_hide_database_details(form)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertEqual(get_user_model().objects.count(), len(cases))

        for user in existing_users:
            user.refresh_from_db()
            self.assertEqual(
                (user.username, user.email, user.password, user.is_staff),
                original_state[user.pk],
            )

    def test_registration_sql_like_phone_payloads_are_rejected_without_creating_users(self):
        payloads = (
            "' OR 1=1 --",
            '" OR "1"="1',
            "'; DROP TABLE auth_user; --",
            "admin'--",
        )

        for index, payload in enumerate(payloads):
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("patient_portal_register_en"),
                    {
                        "full_name": "Injection Regression Patient",
                        "phone": payload,
                        "email": "patient@example.test",
                        "password1": TEST_PASSWORD,
                        "password2": TEST_PASSWORD,
                    },
                    REMOTE_ADDR=f"10.22.0.{index + 1}",
                )

                self.assertEqual(response.status_code, 200)
                form = response.context["form"]
                self.assertEqual(
                    list(form.errors["phone"]),
                    ["Enter a valid phone number."],
                )
                self.assert_form_errors_hide_database_details(form)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertEqual(get_user_model().objects.count(), 0)

    def test_patient_login_sql_like_phone_payloads_never_authenticate(self):
        existing = self.create_user()
        original_state = (existing.username, existing.email, existing.password, existing.is_staff)
        payloads = (
            "' OR 1=1 --",
            '" OR "1"="1',
            "'; DROP TABLE auth_user; --",
            "admin'--",
        )

        for index, payload in enumerate(payloads):
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("login_en"),
                    {
                        "role": "patient",
                        "phone": payload,
                        "password": TEST_PASSWORD,
                    },
                    REMOTE_ADDR=f"10.23.0.{index + 1}",
                )

                self.assertEqual(response.status_code, 200)
                form = response.context["patient_form"]
                self.assertEqual(
                    list(form.errors["phone"]),
                    ["Enter a valid phone number."],
                )
                self.assert_form_errors_hide_database_details(form)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertEqual(get_user_model().objects.count(), 1)

        existing.refresh_from_db()
        self.assertEqual(
            (existing.username, existing.email, existing.password, existing.is_staff),
            original_state,
        )

    def test_doctor_login_sql_like_usernames_never_bypass_staff_authorization(self):
        staff = self.create_user(username="admin", is_staff=True)
        patient = self.create_user(username="ordinary-patient")
        original_state = {
            user.pk: (user.username, user.email, user.password, user.is_staff)
            for user in (staff, patient)
        }
        payloads = (
            "' OR 1=1 --",
            '" OR "1"="1',
            "'; DROP TABLE auth_user; --",
            "admin'--",
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("login_en"),
                    {
                        "role": "doctor",
                        "username": payload,
                        "password": TEST_PASSWORD,
                    },
                )

                self.assertEqual(response.status_code, 200)
                form = response.context["doctor_form"]
                self.assertEqual(list(form.non_field_errors()), [GENERIC_LOGIN_ERROR])
                self.assert_form_errors_hide_database_details(form)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertEqual(get_user_model().objects.count(), 2)

        for user in (staff, patient):
            user.refresh_from_db()
            self.assertEqual(
                (user.username, user.email, user.password, user.is_staff),
                original_state[user.pk],
            )

    def test_registration_and_login_paths_do_not_use_raw_sql_apis(self):
        forbidden_fragments = (
            "connection.cursor(",
            "cursor.execute(",
            ".raw(",
            "RawSQL(",
            ".extra(",
        )

        for relative_path in ("apps/patients/forms.py", "apps/patients/views.py"):
            source = (settings.BASE_DIR / relative_path).read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                with self.subTest(path=relative_path, forbidden=fragment):
                    self.assertNotIn(fragment, source)

    def test_login_uses_phone_and_password(self):
        self.create_user()

        response = self.client.post(
            reverse("patient_portal_login"),
            {
                "phone": "0791234567",
                "password": TEST_PASSWORD,
            },
        )

        self.assertRedirects(response, reverse("patient_portal_dashboard"), fetch_redirect_response=False)

    def test_wrong_login_uses_generic_error(self):
        self.create_user()

        response = self.client.post(
            reverse("patient_portal_login"),
            {
                "phone": "0791234567",
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, auth_error_message("login_generic", "ar"))

    def test_registered_patient_can_access_dashboard(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("patient_portal_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Portal Patient")


class PatientPortalPasswordChangeTests(PatientPortalTestMixin, TestCase):
    def test_anonymous_password_change_redirects_to_portal_login(self):
        response = self.client.get(reverse("patient_portal_password_change"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_authenticated_user_can_change_password_and_keep_session(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("patient_portal_password_change"),
            {
                "old_password": TEST_PASSWORD,
                "new_password1": NEW_TEST_PASSWORD,
                "new_password2": NEW_TEST_PASSWORD,
            },
        )

        self.assertRedirects(response, reverse("patient_portal_account"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_TEST_PASSWORD))
        self.assertFalse(user.check_password(TEST_PASSWORD))
        self.assertEqual(self.client.get(reverse("patient_portal_dashboard")).status_code, 200)

        self.client.logout()
        self.assertFalse(self.client.login(username=user.username, password=TEST_PASSWORD))
        self.assertTrue(self.client.login(username=user.username, password=NEW_TEST_PASSWORD))

    def test_password_change_uses_django_password_validation(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("patient_portal_password_change"),
            {
                "old_password": TEST_PASSWORD,
                "new_password1": "short",
                "new_password2": "short",
            },
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password(TEST_PASSWORD))

    def test_password_change_page_is_no_cache(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("patient_portal_password_change"))

        self.assert_no_cache(response)

    def test_csrf_is_enforced_for_password_change_post(self):
        user = self.create_user()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)

        response = csrf_client.post(
            reverse("patient_portal_password_change"),
            {
                "old_password": TEST_PASSWORD,
                "new_password1": NEW_TEST_PASSWORD,
                "new_password2": NEW_TEST_PASSWORD,
            },
        )

        self.assertEqual(response.status_code, 403)


class PatientPortalAccountTests(PatientPortalTestMixin, TestCase):
    def test_anonymous_account_redirects_to_portal_login(self):
        response = self.client.get(reverse("patient_portal_account"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_authenticated_user_can_access_account_page(self):
        user = self.create_user()
        self.create_appointment(user=user)
        self.client.force_login(user)

        response = self.client.get(reverse("patient_portal_account_en"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Patient")
        self.assertContains(response, "portal@example.test")
        self.assertContains(response, "Linked appointments")

    def test_account_page_masks_phone_and_hides_internal_ids(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)

        response = self.client.get(reverse("patient_portal_account_en"))

        self.assertNotContains(response, user.username)
        self.assertContains(response, "+96279")
        self.assertContains(response, "*****")
        self.assertNotContains(response, str(appointment.public_token))
        self.assertNotContains(response, "Internal ID")
        self.assertNotContains(response, "object_id")

    def test_account_page_does_not_expose_private_operational_content(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            old_status=Appointment.Status.CONFIRMED,
            new_status=Appointment.Status.CANCELLED,
            note="Staff-only status history note.",
        )
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.STATUS_CHANGE,
            app_label="booking",
            model_name="Appointment",
            object_id=str(appointment.id),
            message="Staff-only audit event.",
            metadata={"operation_note": "Internal audit note."},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patient_portal_account_en"))

        self.assertNotContains(response, "Private booking note")
        self.assertNotContains(response, "Staff-only status history note")
        self.assertNotContains(response, "Staff-only audit event")
        self.assertNotContains(response, "Internal audit note")
        self.assertNotContains(response, "/staff/appointments/")
        self.assertNotContains(response, "payment admin")

    def test_account_page_links_to_password_change_and_recovery_policy(self):
        user = self.create_user()
        self.client.force_login(user)

        response = self.client.get(reverse("patient_portal_account_en"))

        self.assertContains(response, f'href="{reverse("patient_portal_password_change_en")}"')
        self.assertContains(response, f'href="{reverse("patient_portal_account_recovery_en")}"')

    def test_account_recovery_routes_use_the_approved_auth_shell_in_both_languages(self):
        route_cases = [
            (
                "patient_portal_account_recovery",
                "ar",
                "rtl",
                "استعادة الحساب",
                "التواصل مع العيادة",
                "العودة لتسجيل الدخول",
                "contact",
                "login",
                "patient_portal_account_recovery_en",
            ),
            (
                "patient_portal_account_recovery_en",
                "en",
                "ltr",
                "Account recovery",
                "Contact the clinic",
                "Back to sign in",
                "contact_en",
                "login_en",
                "patient_portal_account_recovery",
            ),
        ]

        for (
            route_name,
            language,
            direction,
            heading,
            contact_label,
            login_label,
            contact_route,
            login_route,
            language_route,
        ) in route_cases:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "auth/base.html")
                self.assertTemplateNotUsed(response, "base.html")
                self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
                self.assertContains(response, 'class="auth-shell page-account-recovery')
                self.assertContains(response, 'class="auth-card auth-recovery-card"')
                self.assertContains(response, f'<h1 id="auth-title">{heading}</h1>')
                self.assertContains(
                    response,
                    f'<a class="auth-submit" href="{reverse(contact_route)}">',
                )
                self.assertContains(response, contact_label)
                self.assertContains(
                    response,
                    f'<a class="auth-recovery-secondary" href="{reverse(login_route)}">',
                )
                self.assertContains(response, login_label)
                self.assertContains(
                    response,
                    f'href="{reverse(language_route)}" hreflang=',
                )
                self.assertIn("no-store", response["Cache-Control"])
                self.assertNotContains(response, '<footer class="site-footer">')
                self.assertNotContains(response, "data-mobile-booking-cta")
                self.assertNotContains(response, 'class="page-hero"')
                self.assertNotContains(response, 'class="container booking-layout"')
                self.assertNotContains(response, 'class="success-card"')
                self.assertNotContains(response, "trust-note")

    def test_account_recovery_is_concise_and_does_not_collect_sensitive_data(self):
        arabic = self.client.get(reverse("patient_portal_account_recovery"))
        english = self.client.get(reverse("patient_portal_account_recovery_en"))

        self.assertContains(
            arabic,
            "لاستعادة حسابك، تواصل مع العيادة للتحقق من هويتك ومساعدتك في الوصول إلى حسابك.",
        )
        self.assertContains(
            arabic,
            "لن تؤكد هذه الصفحة ما إذا كان رقم هاتف أو بريد إلكتروني مسجلًا لدينا.",
        )
        self.assertContains(
            english,
            "To recover your account, contact the clinic so your identity can be verified and access can be restored safely.",
        )
        self.assertContains(
            english,
            "This page does not confirm whether a phone number or email address is registered.",
        )

        for response in (arabic, english):
            self.assertNotContains(response, "<form")
            self.assertNotContains(response, "<input")
            self.assertNotContains(response, 'type="password"')
            self.assertNotContains(response, "csrfmiddlewaretoken")
            self.assertNotContains(response, "reset token")
            self.assertNotContains(response, "magic link")
            self.assertNotIn("form", response.context)

        for removed_copy in (
            "لا توجد استعادة كلمة مرور عبر البريد الإلكتروني أو واتساب",
            "لا ترسل تشخيصا أو صورا أو تقارير طبية",
            "لا ترسل بريدا، لا ترسل واتساب، ولا تنشئ تذاكر دعم",
        ):
            self.assertNotContains(arabic, removed_copy)

        for removed_copy in (
            "Email password reset and WhatsApp reset are not available",
            "Do not send diagnoses, photos, reports, or sensitive medical details",
            "send email, send WhatsApp messages, or create support tickets",
            "Book Without an Account",
        ):
            self.assertNotContains(english, removed_copy)

    def test_account_recovery_ignores_identifiers_without_account_lookups(self):
        supplied_values = {
            "phone": "0799999999",
            "email": "private-patient@example.com",
            "username": "private-patient-user",
            "user_id": "78421",
        }

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("patient_portal_account_recovery_en"),
                supplied_values,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), 2)
        self.assertTrue(all('FROM "clinic_' in query["sql"] for query in queries))
        for value in supplied_values.values():
            self.assertNotContains(response, value)

    def test_account_recovery_rejects_post_in_both_languages(self):
        for route_name in (
            "patient_portal_account_recovery",
            "patient_portal_account_recovery_en",
        ):
            with self.subTest(route=route_name):
                response = self.client.post(
                    reverse(route_name),
                    {"phone": "0791234567", "email": "patient@example.com"},
                )

                self.assertEqual(response.status_code, 405)


class PatientPortalLinkingTests(PatientPortalTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.client.force_login(self.user)

    def test_linking_requires_login(self):
        self.client.logout()
        appointment = self.create_appointment()

        response = self.client.post(
            reverse("patient_portal_link_appointment"),
            {"public_token": str(appointment.public_token), "phone": "0791234567"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_matching_phone_links_appointment_patient_to_user(self):
        appointment = self.create_appointment()

        response = self.client.post(
            reverse("patient_portal_link_appointment"),
            {"public_token": str(appointment.public_token), "phone": "0791234567"},
        )

        self.assertRedirects(
            response,
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token}),
            fetch_redirect_response=False,
        )
        appointment.patient.refresh_from_db()
        self.assertEqual(appointment.patient.user, self.user)

    def test_wrong_phone_gives_generic_error_and_does_not_link(self):
        appointment = self.create_appointment()

        response = self.client.post(
            reverse("patient_portal_link_appointment"),
            {"public_token": str(appointment.public_token), "phone": "0790000000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_LINK_ERROR)
        appointment.patient.refresh_from_db()
        self.assertIsNone(appointment.patient.user)

    def test_nonexistent_token_gives_generic_error(self):
        response = self.client.post(
            reverse("patient_portal_link_appointment"),
            {"public_token": str(uuid.uuid4()), "phone": "0791234567"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_LINK_ERROR)

    def test_already_linked_patient_to_another_user_cannot_be_stolen(self):
        other_user = self.create_user(
            username="+962790000001",
            email="other@example.test",
            first_name="Other Patient",
        )
        patient = self.create_patient(user=other_user)
        appointment = self.create_appointment(patient=patient)

        response = self.client.post(
            reverse("patient_portal_link_appointment"),
            {"public_token": str(appointment.public_token), "phone": "0791234567"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_LINK_ERROR)
        patient.refresh_from_db()
        self.assertEqual(patient.user, other_user)

    def test_already_linked_appointment_to_same_user_is_noop(self):
        patient = self.create_patient(user=self.user)
        appointment = self.create_appointment(patient=patient)

        response = self.client.post(
            reverse("patient_portal_link_appointment"),
            {"public_token": str(appointment.public_token), "phone": "0791234567"},
        )

        self.assertRedirects(
            response,
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token}),
            fetch_redirect_response=False,
        )
        patient.refresh_from_db()
        self.assertEqual(patient.user, self.user)


class PatientPortalRateLimitTests(PatientPortalTestMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.user = self.create_user()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    @override_settings(PATIENT_PORTAL_LINK_ATTEMPTS_PER_HOUR=1)
    def test_appointment_linking_rate_limit_still_works(self):
        appointment = self.create_appointment()
        post_data = {"public_token": str(appointment.public_token), "phone": "0790000000"}

        self.client.post(reverse("patient_portal_link_appointment"), post_data, REMOTE_ADDR="10.0.0.1")
        response = self.client.post(reverse("patient_portal_link_appointment"), post_data, REMOTE_ADDR="10.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, rate_limits.GENERIC_LINK_RATE_LIMIT_MESSAGE)

    @override_settings(PATIENT_PORTAL_LOGIN_IP_ATTEMPTS_PER_WINDOW=1)
    def test_login_rate_limit_is_localized_without_password_leakage(self):
        self.client.logout()
        post_data = {"phone": "0791234567", "password": "wrong-password"}

        for route_name, language, remote_addr in (
            ("login", "ar", "10.0.0.2"),
            ("login_en", "en", "10.0.0.12"),
        ):
            with self.subTest(language=language):
                self.client.post(reverse(route_name), post_data, REMOTE_ADDR=remote_addr)
                response = self.client.post(reverse(route_name), post_data, REMOTE_ADDR=remote_addr)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, auth_error_message("rate_limit", language))
                self.assertNotContains(response, "wrong-password")

    @override_settings(PATIENT_PORTAL_REGISTRATION_IP_ATTEMPTS_PER_HOUR=1)
    def test_registration_rate_limit_is_localized_without_password_leakage(self):
        self.client.logout()
        post_data = {
            "full_name": "",
            "phone": "0791234567",
            "email": "patient@example.test",
            "password1": TEST_PASSWORD,
            "password2": TEST_PASSWORD,
        }

        for route_name, language, remote_addr in (
            ("patient_portal_register", "ar", "10.0.0.3"),
            ("patient_portal_register_en", "en", "10.0.0.13"),
        ):
            with self.subTest(language=language):
                self.client.post(reverse(route_name), post_data, REMOTE_ADDR=remote_addr)
                response = self.client.post(reverse(route_name), post_data, REMOTE_ADDR=remote_addr)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, auth_error_message("rate_limit", language))
                self.assertNotContains(response, TEST_PASSWORD)

    def test_rate_limit_cache_keys_do_not_include_raw_phone_or_token(self):
        appointment = self.create_appointment()
        post_data = {"public_token": str(appointment.public_token), "phone": "0791234567"}
        observed_keys = []
        original_add = rate_limits.cache.add

        def capture_key(key, *args, **kwargs):
            observed_keys.append(key)
            return original_add(key, *args, **kwargs)

        with patch("apps.patients.rate_limits.cache.add", side_effect=capture_key):
            self.client.post(reverse("patient_portal_link_appointment"), post_data, REMOTE_ADDR="10.0.0.4")

        self.assertTrue(observed_keys)
        for key in observed_keys:
            self.assertNotIn(str(appointment.public_token), key)
            self.assertNotIn("0791234567", key)
            self.assertNotIn("+962791234567", key)

    def test_login_rate_limit_cache_keys_do_not_include_raw_phone_or_password(self):
        self.client.logout()
        observed_keys = []
        original_add = rate_limits.cache.add

        def capture_key(key, *args, **kwargs):
            observed_keys.append(key)
            return original_add(key, *args, **kwargs)

        with patch("apps.patients.rate_limits.cache.add", side_effect=capture_key):
            self.client.post(
                reverse("login"),
                {"phone": "0791234567", "password": "wrong-password"},
                REMOTE_ADDR="10.0.0.5",
            )

        self.assertTrue(observed_keys)
        for key in observed_keys:
            self.assertNotIn("0791234567", key)
            self.assertNotIn("+962791234567", key)
            self.assertNotIn("wrong-password", key)

    def test_registration_rate_limit_cache_keys_do_not_include_raw_phone_or_password(self):
        self.client.logout()
        observed_keys = []
        original_add = rate_limits.cache.add

        def capture_key(key, *args, **kwargs):
            observed_keys.append(key)
            return original_add(key, *args, **kwargs)

        with patch("apps.patients.rate_limits.cache.add", side_effect=capture_key):
            self.client.post(
                reverse("patient_portal_register"),
                {
                    "full_name": "Portal Patient",
                    "phone": "0791234567",
                    "email": "patient@example.test",
                    "password1": TEST_PASSWORD,
                    "password2": TEST_PASSWORD,
                },
                REMOTE_ADDR="10.0.0.6",
            )

        self.assertTrue(observed_keys)
        for key in observed_keys:
            self.assertNotIn("0791234567", key)
            self.assertNotIn("+962791234567", key)
            self.assertNotIn(TEST_PASSWORD, key)
            self.assertNotIn("patient@example.test", key)


class PatientPortalMedicalRecordVisibilityTests(PatientPortalTestMixin, TestCase):
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

    def setUp(self):
        self.user = self.create_user(username="+962790000101", email="records-patient@example.test")
        self.patient = self.create_patient(
            user=self.user,
            full_name="Synthetic Portal Patient",
            phone_raw="0790000101",
            phone_e164="+962790000101",
        )
        self.other_user = self.create_user(username="+962790000202", email="records-other@example.test")
        self.other_patient = self.create_patient(
            user=self.other_user,
            full_name="Synthetic Other Patient",
            phone_raw="0790000202",
            phone_e164="+962790000202",
        )
        self.client.force_login(self.user)

    def synthetic_image_file(self, name="visible-image.jpg", content=b"image-bytes"):
        return SimpleUploadedFile(name, content, content_type="image/jpeg")

    def synthetic_video_file(self, name="visible-video.mp4", content=b"video-bytes"):
        return SimpleUploadedFile(name, content, content_type="video/mp4")

    def create_visit(self, *, patient=None, is_visible_to_patient=False, **kwargs):
        defaults = {
            "patient": patient or self.patient,
            "visit_date": timezone.now(),
            "visit_reason": "Synthetic visit reason.",
            "doctor_notes": "Synthetic doctor note.",
            "diagnosis_plan": "Synthetic manually written plan.",
            "instructions": "Synthetic written instructions.",
            "follow_up_notes": "Synthetic follow-up note.",
            "is_visible_to_patient": is_visible_to_patient,
        }
        defaults.update(kwargs)
        return VisitRecord.objects.create(**defaults)

    def create_note(self, *, patient=None, is_visible_to_patient=False, **kwargs):
        defaults = {
            "patient": patient or self.patient,
            "title": "Synthetic visible note",
            "body": "Synthetic visible note body.",
            "is_visible_to_patient": is_visible_to_patient,
        }
        defaults.update(kwargs)
        return ClinicalNote.objects.create(**defaults)

    def create_media(
        self,
        *,
        patient=None,
        media_type=RecordMedia.MediaType.IMAGE,
        visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
        is_active=True,
        consent_confirmed=False,
        title="Synthetic visible media",
        description="Synthetic visible media description.",
        file=None,
    ):
        patient = patient or self.patient
        if file is None:
            file = (
                self.synthetic_video_file()
                if media_type == RecordMedia.MediaType.SHORT_VIDEO
                else self.synthetic_image_file()
            )
        if visibility == RecordMedia.Visibility.APPROVED_PUBLIC_CASE:
            consent_confirmed = True
            public_case = PublicCase.objects.create(
                patient=patient,
                title=title[:180],
                consent_confirmed=True,
                is_published=True,
            )
            public_case_role = (
                RecordMedia.PublicCaseRole.VIDEO
                if media_type == RecordMedia.MediaType.SHORT_VIDEO
                else RecordMedia.PublicCaseRole.PRIMARY
            )
        else:
            public_case = None
            public_case_role = ""
        return RecordMedia.objects.create(
            patient=patient,
            public_case=public_case,
            public_case_role=public_case_role,
            media_type=media_type,
            file=file,
            visibility=visibility,
            consent_confirmed=consent_confirmed,
            is_active=is_active,
            title=title,
            description=description,
        )

    def test_anonymous_user_cannot_access_medical_records_page(self):
        self.client.logout()

        response = self.client.get(reverse("patient_portal_medical_records"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_authenticated_user_without_linked_patient_gets_safe_empty_state(self):
        unlinked_user = self.create_user(username="+962790000303", email="unlinked@example.test")
        self.create_visit(
            patient=self.other_patient,
            is_visible_to_patient=True,
            visit_reason="Other patient visible visit reason.",
        )
        self.client.force_login(unlinked_user)

        response = self.client.get(reverse("patient_portal_medical_records_en"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No linked patient profile")
        self.assertNotContains(response, "Other patient visible visit reason")
        self.assertNotContains(response, "Synthetic Other Patient")

    def test_linked_patient_can_access_medical_records_page(self):
        response = self.client.get(reverse("patient_portal_medical_records_en"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approved content only")
        self.assertContains(response, "No approved visits are available yet.")

    def test_patient_sees_visible_visit_only(self):
        self.create_visit(
            is_visible_to_patient=True,
            visit_reason="Visible visit reason for patient.",
            doctor_notes="Visible doctor note for patient.",
        )
        self.create_visit(
            is_visible_to_patient=False,
            visit_reason="Private visit reason hidden from patient.",
            doctor_notes="Private doctor note hidden from patient.",
        )
        self.create_visit(
            patient=self.other_patient,
            is_visible_to_patient=True,
            visit_reason="Other patient visible visit hidden from current user.",
        )

        response = self.client.get(reverse("patient_portal_medical_records_en"))

        self.assertContains(response, "Visible visit reason for patient.")
        self.assertContains(response, "Visible doctor note for patient.")
        self.assertNotContains(response, "Private visit reason hidden from patient.")
        self.assertNotContains(response, "Private doctor note hidden from patient.")
        self.assertNotContains(response, "Other patient visible visit hidden from current user.")

    def test_patient_sees_visible_clinical_note_only(self):
        self.create_note(
            is_visible_to_patient=True,
            title="Visible note title for patient",
            body="Visible note body for patient.",
        )
        self.create_note(
            is_visible_to_patient=False,
            title="Private note title hidden from patient",
            body="Private note body hidden from patient.",
        )
        self.create_note(
            patient=self.other_patient,
            is_visible_to_patient=True,
            title="Other patient visible note hidden from current user",
            body="Other patient visible note body.",
        )

        response = self.client.get(reverse("patient_portal_medical_records_en"))

        self.assertContains(response, "Visible note title for patient")
        self.assertContains(response, "Visible note body for patient.")
        self.assertNotContains(response, "Private note title hidden from patient")
        self.assertNotContains(response, "Private note body hidden from patient.")
        self.assertNotContains(response, "Other patient visible note hidden from current user")

    def test_patient_sees_visible_media_metadata_and_patient_route_links_only(self):
        image = self.create_media(
            title="Visible image metadata for patient",
            description="Visible image description for patient.",
            file=self.synthetic_image_file(name="synthetic-visible-image.jpg"),
        )
        video = self.create_media(
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            title="Visible short video metadata for patient",
            description="Visible short video description for patient.",
            file=self.synthetic_video_file(name="synthetic-visible-video.mp4"),
        )

        response = self.client.get(reverse("patient_portal_medical_records_en"))

        image_download_url = reverse(
            "patient_portal_medical_record_media_download_en",
            kwargs={"public_id": image.public_id},
        )
        video_download_url = reverse(
            "patient_portal_medical_record_media_download_en",
            kwargs={"public_id": video.public_id},
        )
        self.assertContains(response, "Visible image metadata for patient")
        self.assertContains(response, "Visible short video metadata for patient")
        self.assertContains(response, f'href="{image_download_url}"')
        self.assertContains(response, f'href="{video_download_url}"')
        self.assertNotContains(response, image.file.name)
        self.assertNotContains(response, video.file.name)
        self.assertNotContains(response, str(settings.PRIVATE_MEDIA_ROOT))
        self.assertNotContains(response, "synthetic-visible-image.jpg")
        self.assertNotContains(response, "synthetic-visible-video.mp4")
        with self.assertRaises(ValueError):
            image.file.url

    def test_patient_does_not_see_private_public_case_inactive_or_other_patient_media(self):
        self.create_media(
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
            title="Private-only media hidden from patient",
        )
        self.create_media(
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            title="Approved public case media hidden from patient",
        )
        self.create_media(
            is_active=False,
            title="Inactive media hidden from patient",
        )
        self.create_media(
            patient=self.other_patient,
            title="Other patient visible media hidden from current user",
        )

        response = self.client.get(reverse("patient_portal_medical_records_en"))

        self.assertNotContains(response, "Private-only media hidden from patient")
        self.assertNotContains(response, "Approved public case media hidden from patient")
        self.assertNotContains(response, "Inactive media hidden from patient")
        self.assertNotContains(response, "Other patient visible media hidden from current user")

    def test_patient_medical_records_page_is_read_only(self):
        response = self.client.post(reverse("patient_portal_medical_records"))

        self.assertEqual(response.status_code, 405)

    def test_anonymous_user_cannot_download_patient_media(self):
        media = self.create_media()
        self.client.logout()

        response = self.client.get(
            reverse("patient_portal_medical_record_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_linked_patient_can_download_own_visible_active_media_by_public_id(self):
        media = self.create_media(
            file=self.synthetic_image_file(name="patient-visible-download.jpg", content=b"download-bytes"),
            title="Downloadable visible media",
        )

        response = self.client.get(
            reverse("patient_portal_medical_record_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("patient-visible-download.jpg", response.get("Content-Disposition", ""))
        self.assertNotIn(str(settings.PRIVATE_MEDIA_ROOT), response.get("Content-Disposition", ""))
        self.assertNotIn(media.file.name, response.get("Content-Disposition", ""))
        self.assertEqual(b"".join(response.streaming_content), b"download-bytes")
        response.close()

    def test_linked_patient_cannot_download_non_patient_visible_media(self):
        blocked_media = [
            self.create_media(
                visibility=RecordMedia.Visibility.PRIVATE_ONLY,
                title="Private media blocked from download",
            ),
            self.create_media(
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                title="Public case media blocked from download",
            ),
            self.create_media(
                is_active=False,
                title="Inactive media blocked from download",
            ),
            self.create_media(
                patient=self.other_patient,
                title="Other patient media blocked from download",
            ),
        ]

        for media in blocked_media:
            with self.subTest(media=media.title):
                response = self.client.get(
                    reverse("patient_portal_medical_record_media_download", kwargs={"public_id": media.public_id})
                )

                self.assertEqual(response.status_code, 404)

    def test_patient_media_response_does_not_expose_private_root_or_public_url(self):
        media = self.create_media(
            file=self.synthetic_image_file(name="safe-visible-image.jpg", content=b"safe-bytes"),
        )

        response = self.client.get(
            reverse("patient_portal_medical_record_media_download", kwargs={"public_id": media.public_id})
        )

        combined_headers = "\n".join(f"{key}: {value}" for key, value in response.headers.items())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(settings.PRIVATE_MEDIA_ROOT), combined_headers)
        self.assertNotIn(media.file.name, combined_headers)
        with self.assertRaises(ValueError):
            media.file.url
        response.close()

    def test_existing_staff_private_media_route_still_requires_staff(self):
        media = self.create_media()

        response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(response.status_code, 403)

    def test_records_root_remains_safe_and_unlisted(self):
        response = self.client.get("/records/")

        self.assertEqual(response.status_code, 404)


class PatientPortalNavigationTests(PatientPortalTestMixin, TestCase):
    def test_authenticated_portal_pages_include_expected_safe_navigation_links(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)
        expected_links = [
            reverse("patient_portal_dashboard"),
            reverse("patient_portal_appointment_list"),
            reverse("patient_portal_medical_records"),
            reverse("patient_portal_link_appointment"),
            reverse("patient_portal_account"),
            reverse("patient_portal_password_change"),
        ]
        page_urls = [
            reverse("patient_portal_dashboard"),
            reverse("patient_portal_appointment_list"),
            reverse("patient_portal_link_appointment"),
            reverse("patient_portal_account"),
            reverse("patient_portal_password_change"),
            reverse("patient_portal_medical_records"),
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token}),
        ]

        for url in page_urls:
            response = self.client.get(url)
            with self.subTest(url=url):
                self.assertEqual(response.status_code, 200)
                for expected_link in expected_links:
                    self.assertContains(response, f'href="{expected_link}"')
                self.assertContains(response, f'action="{reverse("patient_portal_logout")}"')
                self.assertContains(response, 'method="post"')

    def test_logout_remains_post_only(self):
        user = self.create_user()
        self.client.force_login(user)

        get_response = self.client.get(reverse("patient_portal_logout"))
        post_response = self.client.post(reverse("patient_portal_logout"))

        self.assertEqual(get_response.status_code, 405)
        self.assertRedirects(post_response, reverse("login"), fetch_redirect_response=False)
        dashboard_response = self.client.get(reverse("patient_portal_dashboard"))
        self.assertEqual(dashboard_response.status_code, 302)


class PatientPortalPrivacyTests(PatientPortalTestMixin, TestCase):
    def test_user_a_cannot_access_user_b_appointment(self):
        user_a = self.create_user(username="+962790000001", email="a@example.test")
        user_b = self.create_user(username="+962790000002", email="b@example.test")
        appointment = self.create_appointment(user=user_b)
        self.client.force_login(user_a)

        response = self.client.get(
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token})
        )

        self.assertEqual(response.status_code, 404)

    def test_appointment_detail_uses_public_token_not_numeric_id(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)

        token_response = self.client.get(
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token})
        )
        numeric_response = self.client.get(f"/portal/appointments/{appointment.id}/")

        self.assertEqual(token_response.status_code, 200)
        self.assertEqual(numeric_response.status_code, 404)

    def test_english_appointment_detail_numeric_url_returns_404(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)

        response = self.client.get(f"/en/portal/appointments/{appointment.id}/")

        self.assertEqual(response.status_code, 404)

    def test_account_and_dashboard_do_not_expose_raw_public_tokens(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)

        page_urls = [
            reverse("patient_portal_dashboard"),
            reverse("patient_portal_account"),
        ]
        for url in page_urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, str(appointment.public_token))
                self.assertNotContains(response, appointment.confirmation_reference)

    def test_appointment_detail_shows_only_patient_safe_fields(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            old_status=Appointment.Status.CONFIRMED,
            new_status=Appointment.Status.CANCELLED,
            note="Staff-only status history note.",
        )
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.STATUS_CHANGE,
            app_label="booking",
            model_name="Appointment",
            object_id=str(appointment.id),
            message="Staff-only audit event.",
            metadata={"operation_note": "Internal audit note."},
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("patient_portal_appointment_detail_en", kwargs={"public_token": appointment.public_token})
        )

        self.assertContains(response, "New consultation")
        self.assertContains(response, "Confirmed")
        self.assertNotContains(response, "Private booking note")
        self.assertNotContains(response, "Staff-only status history note")
        self.assertNotContains(response, "Staff-only audit event")
        self.assertNotContains(response, "Internal audit note")
        self.assertNotContains(response, "/staff/appointments/")
        self.assertNotContains(response, str(appointment.public_token))

    def test_patient_pages_do_not_link_staff_operation_urls(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)
        page_urls = [
            reverse("patient_portal_dashboard"),
            reverse("patient_portal_account"),
            reverse("patient_portal_password_change"),
            reverse("patient_portal_link_appointment"),
            reverse("patient_portal_appointment_list"),
            reverse("patient_portal_medical_records"),
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token}),
        ]
        blocked_fragments = [
            "/staff/appointments/",
            "/cancel/",
            "/reschedule/",
            "/arrived/",
            "/complete/",
            "/no-show/",
        ]

        for url in page_urls:
            response = self.client.get(url)
            with self.subTest(url=url):
                self.assertEqual(response.status_code, 200)
                for fragment in blocked_fragments:
                    self.assertNotContains(response, fragment)

    def test_patient_pages_do_not_expose_private_operational_strings(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            old_status=Appointment.Status.CONFIRMED,
            new_status=Appointment.Status.RESCHEDULED,
            note="Status history private note.",
        )
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.STATUS_CHANGE,
            app_label="booking",
            model_name="Appointment",
            object_id=str(appointment.id),
            message="Audit log private message.",
            metadata={"operation_note": "Audit metadata private note."},
        )
        self.client.force_login(user)
        page_urls = [
            reverse("patient_portal_dashboard"),
            reverse("patient_portal_account"),
            reverse("patient_portal_appointment_list"),
            reverse("patient_portal_medical_records"),
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token}),
        ]
        blocked_text = [
            "Private booking note",
            "Status history private note",
            "Audit log private message",
            "Audit metadata private note",
            "operation_note",
        ]

        for url in page_urls:
            response = self.client.get(url)
            with self.subTest(url=url):
                self.assertEqual(response.status_code, 200)
                for text in blocked_text:
                    self.assertNotContains(response, text)

    def test_patient_safe_status_label_for_no_show_is_missed(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user, status=Appointment.Status.NO_SHOW)
        self.client.force_login(user)

        response = self.client.get(
            reverse("patient_portal_appointment_detail_en", kwargs={"public_token": appointment.public_token})
        )

        self.assertContains(response, "Missed")
        self.assertNotContains(response, "No-show")

    def test_portal_pages_are_no_cache(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)

        authenticated_urls = [
            reverse("patient_portal_dashboard"),
            reverse("patient_portal_account"),
            reverse("patient_portal_password_change"),
            reverse("patient_portal_link_appointment"),
            reverse("patient_portal_appointment_list"),
            reverse("patient_portal_medical_records"),
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token}),
        ]
        for url in authenticated_urls:
            with self.subTest(url=url):
                self.assert_no_cache(self.client.get(url))

        anonymous_client = Client()
        for url in [
            reverse("patient_portal_login"),
            reverse("patient_portal_register"),
            reverse("patient_portal_account_recovery"),
        ]:
            with self.subTest(url=url):
                self.assert_no_cache(anonymous_client.get(url))

    def test_csrf_is_enforced_for_login_register_and_link_posts(self):
        csrf_client = Client(enforce_csrf_checks=True)
        login_response = csrf_client.post(
            reverse("patient_portal_login"),
            {"phone": "0791234567", "password": TEST_PASSWORD},
        )
        register_response = csrf_client.post(
            reverse("patient_portal_register"),
            {
                "full_name": "Portal Patient",
                "phone": "0791234567",
                "password1": TEST_PASSWORD,
                "password2": TEST_PASSWORD,
            },
        )

        user = self.create_user()
        appointment = self.create_appointment()
        csrf_client.force_login(user)
        link_response = csrf_client.post(
            reverse("patient_portal_link_appointment"),
            {"public_token": str(appointment.public_token), "phone": "0791234567"},
        )

        self.assertEqual(login_response.status_code, 403)
        self.assertEqual(register_response.status_code, 403)
        self.assertEqual(link_response.status_code, 403)

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

    def test_patient_medical_record_route_requires_authentication(self):
        response = self.client.get("/portal/medical-records/")

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
