
from datetime import datetime, time, timedelta
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog
from apps.patients.forms import GENERIC_LINK_ERROR, GENERIC_LOGIN_ERROR, GENERIC_REGISTRATION_ERROR
from apps.patients import rate_limits
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


class PatientPortalAuthenticationTests(PatientPortalTestMixin, TestCase):
    def test_anonymous_dashboard_redirects_to_portal_login(self):
        response = self.client.get(reverse("patient_portal_dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("patient_portal_login"), response["Location"])

    def test_anonymous_appointment_detail_redirects_to_portal_login(self):
        appointment = self.create_appointment()

        response = self.client.get(
            reverse("patient_portal_appointment_detail", kwargs={"public_token": appointment.public_token})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("patient_portal_login"), response["Location"])

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
        self.assertTrue(user.check_password(TEST_PASSWORD))
        self.assertNotEqual(user.password, TEST_PASSWORD)
        self.assertEqual(user.email, "patient@example.test")

    def test_duplicate_phone_registration_uses_generic_error(self):
        self.create_user()

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

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_REGISTRATION_ERROR)
        self.assertEqual(get_user_model().objects.count(), 1)

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
        self.assertContains(response, GENERIC_LOGIN_ERROR)

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
        self.assertIn(reverse("patient_portal_login"), response["Location"])

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
        self.assertIn(reverse("patient_portal_login"), response["Location"])

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

    def test_account_recovery_page_is_static_and_does_not_collect_sensitive_data(self):
        response = self.client.get(reverse("patient_portal_account_recovery_en"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "clinic-assisted")
        self.assertContains(response, "does not confirm")
        self.assertNotContains(response, "<form")
        self.assertNotContains(response, 'name="phone"')
        self.assertNotContains(response, 'name="email"')

    def test_account_recovery_rejects_post(self):
        response = self.client.post(reverse("patient_portal_account_recovery"), {"phone": "0791234567"})

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
        self.assertIn(reverse("patient_portal_login"), response["Location"])

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
    def test_login_rate_limit_uses_generic_error_without_password_leakage(self):
        self.client.logout()
        post_data = {"phone": "0791234567", "password": "wrong-password"}

        self.client.post(reverse("patient_portal_login"), post_data, REMOTE_ADDR="10.0.0.2")
        response = self.client.post(reverse("patient_portal_login"), post_data, REMOTE_ADDR="10.0.0.2")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, rate_limits.GENERIC_PORTAL_RATE_LIMIT_MESSAGE)
        self.assertNotContains(response, "wrong-password")

    @override_settings(PATIENT_PORTAL_REGISTRATION_IP_ATTEMPTS_PER_HOUR=1)
    def test_registration_rate_limit_uses_generic_error_without_password_leakage(self):
        self.client.logout()
        post_data = {
            "full_name": "",
            "phone": "0791234567",
            "email": "patient@example.test",
            "password1": TEST_PASSWORD,
            "password2": TEST_PASSWORD,
        }

        self.client.post(reverse("patient_portal_register"), post_data, REMOTE_ADDR="10.0.0.3")
        response = self.client.post(reverse("patient_portal_register"), post_data, REMOTE_ADDR="10.0.0.3")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, rate_limits.GENERIC_PORTAL_RATE_LIMIT_MESSAGE)
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


class PatientPortalNavigationTests(PatientPortalTestMixin, TestCase):
    def test_authenticated_portal_pages_include_expected_safe_navigation_links(self):
        user = self.create_user()
        appointment = self.create_appointment(user=user)
        self.client.force_login(user)
        expected_links = [
            reverse("patient_portal_dashboard"),
            reverse("patient_portal_appointment_list"),
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
        self.assertRedirects(post_response, reverse("patient_portal_login"), fetch_redirect_response=False)
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

    def test_upload_whatsapp_and_medical_record_routes_remain_absent(self):
        blocked_paths = [
            "/uploads/",
            "/portal/uploads/",
            "/whatsapp/webhook/",
            "/api/whatsapp/",
            "/whatsapp/api/",
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
