from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from . import review_moderation
from .models import AuditLog, PublicReview


class SharedReviewModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser(username="synthetic-shared-moderator")

    def setUp(self):
        self.client.force_login(self.staff)
        self.review = PublicReview.objects.create(
            source=PublicReview.Source.PATIENT_PORTAL, reviewer_name="Synthetic patient",
            body="Patient-authored feedback", rating=4, language="en",
            is_approved_for_publication=True, is_featured=True, display_order=23,
        )
        self.admin_url = reverse("admin:core_publicreview_change", args=[self.review.pk])
        self.dashboard_url = reverse("dashboard_patient_review_visibility", args=[self.review.pk]) + "?lang=en"
        self.delete_url = reverse("dashboard_patient_review_delete", args=[self.review.pk]) + "?lang=en"

    def snapshot(self):
        return PublicReview.objects.filter(pk=self.review.pk).values().get()

    def action_data(self, surface):
        if surface == "admin":
            form = self.client.get(self.admin_url).context["adminform"].form
            review = form.instance
            action = "hide" if review.is_active and review.is_approved_for_publication else "show"
            return self.admin_url, {"review_version": form["review_version"].value(), "moderation_action": action}
        response = self.client.get(reverse("dashboard_patient_reviews") + "?lang=en")
        item = next(item for item in response.context["review_items"] if item["review"].pk == self.review.pk)
        return self.dashboard_url, {
            "review_version": item["form"]["review_version"].value(), "moderation_action": item["action"],
        }

    def test_both_surfaces_use_shared_signing_validation_and_transition_for_all_visibility_states(self):
        for surface in ("admin", "dashboard"):
            for active, approved in ((False, False), (False, True), (True, False), (True, True)):
                with self.subTest(surface=surface, active=active, approved=approved):
                    PublicReview.objects.filter(pk=self.review.pk).update(
                        is_active=active, is_approved_for_publication=approved,
                    )
                    before = self.snapshot()
                    with patch.object(review_moderation, "sign_review_revision", wraps=review_moderation.sign_review_revision) as sign:
                        url, data = self.action_data(surface)
                    self.assertEqual(sign.call_count, 1)
                    with (
                        patch.object(review_moderation, "validate_review_revision", wraps=review_moderation.validate_review_revision) as validate,
                        patch.object(review_moderation, "set_patient_review_visibility", wraps=review_moderation.set_patient_review_visibility) as transition,
                    ):
                        response = self.client.post(url, data)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(validate.call_count, 1)
                    self.assertEqual(transition.call_count, 1)
                    self.assertEqual(validate.call_args.args[1].pk, self.review.pk)
                    self.assertEqual(transition.call_args.args[0].pk, self.review.pk)
                    self.assertEqual(transition.call_args.args[1], data["moderation_action"])
                    after = self.snapshot()
                    self.assertTrue(after["is_active"])
                    self.assertEqual(after["is_approved_for_publication"], not (active and approved))
                    self.assertNotEqual(after["updated_at"], before["updated_at"])
                    for field in before.keys() - {"is_active", "is_approved_for_publication", "updated_at"}:
                        self.assertEqual(after[field], before[field], field)

    def test_both_surfaces_fail_closed_when_shared_integrity_validation_rejects(self):
        for surface in ("admin", "dashboard"):
            with self.subTest(surface=surface):
                url, data = self.action_data(surface)
                before = self.snapshot()
                with (
                    patch.object(review_moderation, "validate_review_revision", side_effect=review_moderation.StaleReviewRevision) as validate,
                    patch.object(review_moderation, "set_patient_review_visibility", wraps=review_moderation.set_patient_review_visibility) as transition,
                ):
                    response = self.client.post(url, data)
                self.assertEqual(response.status_code, 200 if surface == "admin" else 400)
                self.assertEqual(validate.call_count, 1)
                transition.assert_not_called()
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(AuditLog.objects.filter(model_name="PublicReview").exists())

    def test_changes_on_either_surface_invalidate_forms_on_both_surfaces(self):
        for surface in ("admin", "dashboard"):
            with self.subTest(changed_by=surface):
                pending = {name: self.action_data(name) for name in ("admin", "dashboard")}
                delete_form = self.client.get(self.delete_url).context["form"]
                stale_delete = {"review_version": delete_form["review_version"].value(), "post": "yes"}
                self.assertEqual(self.client.post(*pending[surface]).status_code, 302)
                before = self.snapshot()
                for name, (url, data) in pending.items():
                    self.assertEqual(self.client.post(url, data).status_code, 200 if name == "admin" else 400)
                    self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.client.post(self.delete_url, stale_delete).status_code, 400)
                self.assertEqual(self.snapshot(), before)

    def test_tokens_cannot_cross_surface_namespaces(self):
        admin_url, admin_data = self.action_data("admin")
        dashboard_url, dashboard_data = self.action_data("dashboard")
        before = self.snapshot()
        for url, data, token, status in (
            (admin_url, admin_data, dashboard_data["review_version"], 200),
            (dashboard_url, dashboard_data, admin_data["review_version"], 400),
        ):
            self.assertEqual(self.client.post(url, data | {"review_version": token}).status_code, status)
            self.assertEqual(self.snapshot(), before)

    def test_shared_source_guard_rejects_imported_reviews_even_with_valid_revision_tokens(self):
        for source in (PublicReview.Source.GOOGLE, PublicReview.Source.OTHER):
            with self.subTest(source=source):
                imported = PublicReview.objects.create(
                    source=source, body="Synthetic imported feedback", rating=5, language="en", is_active=False,
                )
                before = PublicReview.objects.filter(pk=imported.pk).values().get()
                self.assertFalse(review_moderation.is_patient_review(imported))
                self.assertFalse(review_moderation.patient_reviews().filter(pk=imported.pk).exists())
                for action in ("hide", "show"):
                    with self.assertRaises(PermissionDenied):
                        review_moderation.set_patient_review_visibility(imported, action)
                # Admin still signs revisions for imported reviews; its token cannot
                # bypass the Dashboard's shared patient-only queryset.
                url = reverse("admin:core_publicreview_change", args=[imported.pk])
                form = self.client.get(url).context["adminform"].form
                with patch.object(review_moderation, "set_patient_review_visibility", wraps=review_moderation.set_patient_review_visibility) as transition:
                    self.assertEqual(self.client.post(url, {
                        "review_version": form["review_version"].value(),
                        "is_approved_for_publication": "on", "display_order": 0,
                    }).status_code, 302)
                transition.assert_not_called()
                imported.refresh_from_db()
                self.assertFalse(imported.is_active)
                self.assertTrue(imported.is_approved_for_publication)
                for route in ("dashboard_patient_review_visibility", "dashboard_patient_review_delete"):
                    url = reverse(route, args=[imported.pk])
                    self.assertEqual(self.client.post(url, {
                        "review_version": form["review_version"].value(), "moderation_action": "show", "post": "yes",
                    }).status_code, 404)
                after = PublicReview.objects.filter(pk=imported.pk).values().get()
                for field in before.keys() - {"is_approved_for_publication", "updated_at"}:
                    self.assertEqual(after[field], before[field], field)

    def test_shared_transition_rejects_invalid_actions_and_hide_preserves_legacy_inactive_state(self):
        before = self.snapshot()
        for action in (None, "", "approve", "delete"):
            with self.assertRaises(PermissionDenied):
                review_moderation.set_patient_review_visibility(self.review, action)
            self.assertEqual(self.snapshot(), before)
        self.review.is_active = False
        self.review.save()
        review_moderation.set_patient_review_visibility(self.review, "hide")
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_active)
        self.assertFalse(self.review.is_approved_for_publication)
