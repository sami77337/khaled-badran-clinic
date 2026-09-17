from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AuditLog, PublicReview
from apps.patients.models import Patient


class PatientAccountCloseTests(TestCase):
    password = "Synthetic-close-account-914!"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="+12025550177",
            password=self.password,
            first_name="Synthetic Patient",
            email="synthetic-close@example.test",
        )
        self.patient = Patient.objects.create(
            user=self.user,
            full_name="Synthetic Patient",
            phone_raw=self.user.username,
            phone_e164=self.user.username,
        )
        self.client.force_login(self.user)

    def test_account_page_links_to_localized_close_workflow(self):
        cases = (
            ("patient_portal_account", "patient_portal_account_close", "إغلاق الحساب"),
            ("patient_portal_account_en", "patient_portal_account_close_en", "Close Account"),
        )
        for account_route, close_route, label in cases:
            with self.subTest(account_route=account_route):
                response = self.client.get(reverse(account_route))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, reverse(close_route))
                self.assertContains(response, label)

    def test_close_requires_current_password_and_explicit_confirmation(self):
        url = reverse("patient_portal_account_close_en")
        wrong = self.client.post(
            url,
            {"current_password": "wrong-password", "confirm": "on"},
        )
        self.assertEqual(wrong.status_code, 200)
        self.assertContains(wrong, "The current password is incorrect.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

        missing_confirmation = self.client.post(
            url,
            {"current_password": self.password},
        )
        self.assertEqual(missing_confirmation.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_close_disables_login_but_retains_patient_record_and_unpublishes_review(self):
        review = PublicReview.objects.create(
            submitted_by=self.user,
            reviewer_name="Synthetic Reviewer",
            body="Synthetic public review.",
            rating=5,
            language=PublicReview.Language.ENGLISH,
            source=PublicReview.Source.PATIENT_PORTAL,
            is_approved_for_publication=True,
            is_active=True,
            is_featured=True,
        )
        response = self.client.post(
            reverse("patient_portal_account_close_en"),
            {"current_password": self.password, "confirm": "on"},
        )
        self.assertRedirects(
            response,
            reverse("patient_portal_account_closed_en"),
            fetch_redirect_response=False,
        )

        self.user.refresh_from_db()
        self.patient.refresh_from_db()
        review.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.patient.user_id, self.user.pk)
        self.assertFalse(review.is_active)
        self.assertFalse(review.is_featured)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(
            self.client.login(username=self.user.username, password=self.password)
        )
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.user,
                action=AuditLog.Action.STATUS_CHANGE,
                metadata__account_closed=True,
            ).exists()
        )
        self.assertEqual(
            self.client.get(reverse("patient_portal_account_closed_en")).status_code,
            200,
        )

    def test_staff_accounts_cannot_use_patient_close_workflow(self):
        staff = get_user_model().objects.create_user(
            username="synthetic-staff-close",
            password=self.password,
            is_staff=True,
        )
        self.client.force_login(staff)
        self.assertEqual(
            self.client.get(reverse("patient_portal_account_close_en")).status_code,
            403,
        )
        staff.refresh_from_db()
        self.assertTrue(staff.is_active)

    def test_anonymous_close_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("patient_portal_account_close_en"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login_en"), response.url)
