from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import PublicReview


class ReviewModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser(username="synthetic-moderator")
        cls.patient = get_user_model().objects.create_user(username="synthetic-review-patient")

    def setUp(self):
        self.client.force_login(self.staff)
        self.review = PublicReview.objects.create(
            submitted_by=self.patient, source=PublicReview.Source.PATIENT_PORTAL,
            reviewer_name="Patient display", rating=4, body="Original patient review.", language="en",
        )
        self.url = reverse("admin:core_publicreview_change", args=[self.review.pk])
        self.list_url = reverse("admin:core_publicreview_changelist")

    def moderation_data(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        return {
            "review_version": form["review_version"].value(), "is_approved_for_publication": "on",
            "is_active": "on", "is_featured": "on", "display_order": 2, "_save": "Save",
        }

    def list_data(self):
        response = self.client.get(self.list_url)
        formset = response.context["cl"].formset
        form = formset.forms[0]
        self.assertContains(response, f'name="{form.prefix}-review_version"')
        return {
            f"{formset.prefix}-TOTAL_FORMS": 1, f"{formset.prefix}-INITIAL_FORMS": 1,
            f"{formset.prefix}-MAX_NUM_FORMS": 1000, f"{form.prefix}-id": self.review.pk,
            f"{form.prefix}-review_version": form["review_version"].value(),
            f"{form.prefix}-is_approved_for_publication": "on", f"{form.prefix}-is_active": "on",
            f"{form.prefix}-display_order": 0, "_save": "Save",
        }

    def patient_edit(self):
        self.client.force_login(self.patient)
        response = self.client.post(reverse("patient_portal_review_edit_en", args=[self.review.pk]), {
            "reviewer_name": "Updated display", "rating": 2, "body": "New patient-authored text.",
        })
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.staff)

    def test_admin_cannot_create_reviews(self):
        url = reverse("admin:core_publicreview_add")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"rating": 5, "body": "Staff text"}).status_code, 403)

    def test_admin_can_moderate_but_cannot_rewrite_patient_fields(self):
        data = self.moderation_data() | {
            "body": "Staff rewrite", "rating": 5, "reviewer_name": "Staff rewrite",
            "submitted_by": self.staff.pk, "source": "google", "language": "ar",
        }
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.body, "Original patient review.")
        self.assertEqual(self.review.reviewer_name, "Patient display")
        self.assertEqual(self.review.rating, 4)
        self.assertEqual(self.review.submitted_by, self.patient)
        self.assertEqual(self.review.source, PublicReview.Source.PATIENT_PORTAL)
        self.assertEqual(self.review.language, "en")
        self.assertTrue(self.review.is_approved_for_publication)
        self.assertTrue(self.review.is_featured)
        self.assertEqual(self.review.display_order, 2)

    def test_stale_detail_approval_is_rejected_after_patient_edit(self):
        data = self.moderation_data()
        self.patient_edit()
        response = self.client.post(self.url, data)
        self.assertContains(response, "This review changed after you opened it.")
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_approved_for_publication)
        self.assertEqual(self.review.body, "New patient-authored text.")
        self.assertEqual(self.client.post(self.url, self.moderation_data()).status_code, 302)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_approved_for_publication)

    def test_stale_list_approval_is_rejected_after_patient_edit(self):
        data = self.list_data()
        self.patient_edit()
        response = self.client.post(self.list_url, data)
        self.assertContains(response, "This review changed after you opened it.")
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_approved_for_publication)
        self.assertEqual(self.review.body, "New patient-authored text.")

    def test_current_list_approval_succeeds(self):
        self.assertEqual(self.client.post(self.list_url, self.list_data()).status_code, 302)
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_approved_for_publication)
        updated_at = self.review.updated_at
        with patch("django.core.signing.time.time", return_value=1):
            unchanged = self.list_data()
        self.assertEqual(self.client.post(self.list_url, unchanged).status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.updated_at, updated_at)

    def test_missing_and_tampered_revision_cannot_approve(self):
        for token in ("", "forged-revision"):
            response = self.client.post(self.url, self.moderation_data() | {"review_version": token})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
            self.review.refresh_from_db()
            self.assertFalse(self.review.is_approved_for_publication)

    def test_revision_for_another_review_cannot_approve(self):
        data = self.moderation_data()
        other = PublicReview.objects.create(reviewer_name="Imported", body="Imported text", language="en", rating=5)
        response = self.client.post(reverse("admin:core_publicreview_change", args=[other.pk]), data)
        self.assertContains(response, "This review changed after you opened it.")
        other.refresh_from_db()
        self.assertFalse(other.is_approved_for_publication)
