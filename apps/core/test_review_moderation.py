from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import PublicReview
from .showcase import approved_reviews, review_source_summary


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReviewModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username="synthetic-moderator", is_staff=True)
        cls.staff.user_permissions.set(Permission.objects.filter(
            content_type__app_label="core", codename__in=(
                "view_publicreview", "change_publicreview", "delete_publicreview",
            ),
        ))
        cls.patient = get_user_model().objects.create_user(username="synthetic-review-patient")

    def setUp(self):
        self.client.force_login(self.staff)
        self.review = PublicReview.objects.create(
            submitted_by=self.patient, source=PublicReview.Source.PATIENT_PORTAL,
            reviewer_name="Patient display", rating=4, body="Original patient review.", language="en",
        )
        self.url = reverse("admin:core_publicreview_change", args=[self.review.pk])
        self.list_url = reverse("admin:core_publicreview_changelist")

    def moderation_data(self, visibility="show"):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        return {
            "review_version": form["review_version"].value(),
            "is_approved_for_publication": visibility, "_save": "Save",
        }

    def list_data(self, visibility="show"):
        response = self.client.get(self.list_url)
        formset = response.context["cl"].formset
        form = formset.forms[0]
        self.assertContains(response, f'name="{form.prefix}-review_version"')
        return {
            f"{formset.prefix}-TOTAL_FORMS": 1, f"{formset.prefix}-INITIAL_FORMS": 1,
            f"{formset.prefix}-MAX_NUM_FORMS": 1000, f"{form.prefix}-id": self.review.pk,
            f"{form.prefix}-review_version": form["review_version"].value(),
            f"{form.prefix}-is_approved_for_publication": visibility, "_save": "Save",
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
            "is_active": "", "is_featured": "on", "display_order": 900,
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
        self.assertTrue(self.review.is_active)
        self.assertFalse(self.review.is_featured)
        self.assertEqual(self.review.display_order, 0)

    def test_stale_detail_hide_is_rejected_after_patient_edit(self):
        data = self.moderation_data("hide")
        self.patient_edit()
        response = self.client.post(self.url, data)
        self.assertContains(response, "This review changed after you opened it.")
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_approved_for_publication)
        self.assertEqual(self.review.body, "New patient-authored text.")
        self.assertEqual(self.client.post(self.url, self.moderation_data("hide")).status_code, 302)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_approved_for_publication)
        self.assertEqual(self.review.body, "New patient-authored text.")

    def test_stale_list_hide_is_rejected_after_patient_edit(self):
        data = self.list_data("hide")
        self.patient_edit()
        response = self.client.post(self.list_url, data)
        self.assertContains(response, "This review changed after you opened it.")
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_approved_for_publication)
        self.assertEqual(self.review.body, "New patient-authored text.")
        self.assertEqual(self.client.post(self.list_url, self.list_data("hide")).status_code, 302)
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

    def test_staff_can_hide_show_and_delete_immediately_published_patient_review(self):
        self.patient_edit()
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_approved_for_publication)
        self.assertContains(self.client.get(reverse("reviews_en")), self.review.body)
        for url, payload in ((self.url, self.moderation_data), (self.list_url, self.list_data)):
            for visibility in ("hide", "show"):
                self.assertEqual(self.client.post(url, payload(visibility)).status_code, 302)
                self.review.refresh_from_db()
                published = visibility == "show"
                self.assertEqual(self.review.is_approved_for_publication, published)
                self.assertTrue(self.review.is_active)
                self.assertEqual([r.pk for r in approved_reviews()], [self.review.pk] if published else [])
                self.assertEqual(review_source_summary(),
                                 {"average_rating": "2.00", "review_count": 1} if published else None)
                for route in ("home", "home_en", "reviews", "reviews_en"):
                    response = self.client.get(reverse(route))
                    if published:
                        self.assertContains(response, self.review.body)
                        self.assertContains(response, '<strong dir="ltr">2.00</strong>', html=True)
                    else:
                        self.assertNotContains(response, self.review.body)
                        self.assertNotContains(response, '<strong dir="ltr">2.00</strong>', html=True)
                    if route.startswith("reviews"):
                        self.assertEqual(response.context["review_summary"], review_source_summary())
        delete_url = reverse("admin:core_publicreview_delete", args=[self.review.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())

    def test_show_restores_legacy_inactive_review_and_hide_has_one_state(self):
        for url, payload in ((self.url, self.moderation_data), (self.list_url, self.list_data)):
            for approved in (False, True):
                PublicReview.objects.filter(pk=self.review.pk).update(
                    is_active=False, is_approved_for_publication=approved,
                )
                form = self.client.get(self.url).context["adminform"].form
                self.assertEqual(form["is_approved_for_publication"].value(), "hide")
                self.assertEqual(self.client.post(url, payload("show")).status_code, 302)
                self.review.refresh_from_db()
                self.assertTrue(self.review.is_approved_for_publication and self.review.is_active)
                self.assertEqual(self.client.post(url, payload("hide")).status_code, 302)
                self.review.refresh_from_db()
                self.assertFalse(self.review.is_approved_for_publication)
                self.assertTrue(self.review.is_active)

    def test_list_crafted_post_cannot_rewrite_content_or_ordering(self):
        data = self.list_data() | {
            "form-0-reviewer_name": "Forged staff name", "form-0-rating": 1,
            "form-0-body": "Forged staff text", "form-0-is_featured": "on",
            "form-0-display_order": 900, "form-0-is_active": "",
        }
        self.assertEqual(self.client.post(self.list_url, data).status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual((self.review.reviewer_name, self.review.rating, self.review.body),
                         ("Patient display", 4, "Original patient review."))
        self.assertFalse(self.review.is_featured)
        self.assertEqual(self.review.display_order, 0)
        self.assertTrue(self.review.is_active and self.review.is_approved_for_publication)

    def test_imported_content_and_ordering_are_preserved(self):
        PublicReview.objects.filter(pk=self.review.pk).update(
            source=PublicReview.Source.GOOGLE, submitted_by=None,
            source_reference="synthetic-import-reference", is_featured=True, display_order=7,
        )
        data = self.moderation_data() | {
            "reviewer_name": "Forged", "rating": 1, "body": "Forged",
            "source_reference": "forged-reference", "display_order": 999,
        }
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual((self.review.reviewer_name, self.review.rating, self.review.body),
                         ("Patient display", 4, "Original patient review."))
        self.assertEqual(self.review.source, PublicReview.Source.GOOGLE)
        self.assertEqual(self.review.source_reference, "synthetic-import-reference")
        self.assertIsNone(self.review.submitted_by)
        self.assertTrue(self.review.is_featured)
        self.assertEqual(self.review.display_order, 7)

    def test_ar_en_controls_are_hide_show_delete_only(self):
        for language, hide, show, delete in (("ar", "إخفاء", "إظهار", "حذف"), ("en", "Hide", "Show", "Delete")):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            for url in (self.url, self.list_url):
                response = self.client.get(url)
                self.assertContains(response, f'<option value="hide" selected>{hide}</option>', html=True)
                self.assertContains(response, f'<option value="show">{show}</option>', html=True)
                for field in ("is_active", "is_featured", "display_order"):
                    self.assertNotContains(response, field)
                for label in ("Feature", "Display order", "Deactivate"):
                    self.assertNotContains(response, label)
            detail = self.client.get(self.url)
            self.assertContains(detail, f'class="deletelink">{delete}</a>')
            for field in ("reviewer_name", "rating", "body"):
                self.assertNotContains(detail, f'name="{field}"')
            self.assertContains(self.client.get(self.list_url), f'<option value="delete_selected">{delete}</option>', html=True)

    def test_unauthorized_staff_and_patients_cannot_moderate_or_delete(self):
        data, list_data = self.moderation_data(), self.list_data()
        delete_url = reverse("admin:core_publicreview_delete", args=[self.review.pk])
        unauthorized = get_user_model().objects.create_user(username="synthetic-unprivileged-staff", is_staff=True)
        for user, expected in ((unauthorized, 403), (self.patient, 302)):
            self.client.force_login(user)
            for url, payload in ((self.url, data), (self.list_url, list_data), (delete_url, {"post": "yes"}),
                                 (self.list_url, {"action": "delete_selected", "_selected_action": self.review.pk, "post": "yes"})):
                self.assertEqual(self.client.post(url, payload).status_code, expected)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_approved_for_publication)
        self.assertEqual(self.review.body, "Original patient review.")

    def test_change_permission_alone_cannot_delete(self):
        moderator = get_user_model().objects.create_user(username="synthetic-change-only-staff", is_staff=True)
        moderator.user_permissions.add(Permission.objects.get(content_type__app_label="core", codename="change_publicreview"))
        self.client.force_login(moderator)
        self.assertEqual(self.client.post(self.url, self.moderation_data()).status_code, 302)
        delete_url = reverse("admin:core_publicreview_delete", args=[self.review.pk])
        self.assertEqual(self.client.post(delete_url, {"post": "yes"}).status_code, 403)
        self.assertNotContains(self.client.get(self.url), 'class="deletelink"')
        self.assertNotContains(self.client.get(self.list_url), 'value="delete_selected"')
        self.assertTrue(PublicReview.objects.filter(pk=self.review.pk).exists())

    def test_view_only_staff_cannot_moderate_or_delete_with_crafted_posts(self):
        detail_data, list_data = self.moderation_data(), self.list_data()
        viewer = get_user_model().objects.create_user(username="synthetic-review-viewer", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(
            content_type__app_label="core", codename="view_publicreview",
        ))
        self.client.force_login(viewer)
        for url in (self.url, self.list_url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, '<option value="show"')
            self.assertNotContains(response, 'class="deletelink"')
        delete_url = reverse("admin:core_publicreview_delete", args=[self.review.pk])
        for url, data in ((self.url, detail_data), (self.list_url, list_data),
                          (delete_url, {"post": "yes"})):
            self.assertEqual(self.client.post(url, data).status_code, 403)
        self.client.post(self.list_url, {
            "action": "delete_selected", "_selected_action": self.review.pk, "post": "yes",
        })
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_approved_for_publication)
        self.assertEqual(self.review.body, "Original patient review.")

    def test_authorized_bulk_delete_permanently_removes_public_review_and_aggregate(self):
        self.patient_edit()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        client.get(self.list_url)
        response = client.post(self.list_url, {
            "action": "delete_selected", "_selected_action": self.review.pk, "post": "yes",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assertIsNone(review_source_summary())
        for route in ("home", "home_en", "reviews", "reviews_en"):
            self.assertNotContains(self.client.get(reverse(route)), "New patient-authored text.")

    def test_all_staff_mutations_require_csrf_and_delete_get_is_read_only(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        delete_url = reverse("admin:core_publicreview_delete", args=[self.review.pk])
        for url, data in ((self.url, self.moderation_data()), (self.list_url, self.list_data()),
                          (delete_url, {"post": "yes"}), (self.list_url, {
                              "action": "delete_selected", "_selected_action": self.review.pk, "post": "yes",
                          })):
            self.assertEqual(client.post(url, data).status_code, 403)
        self.assertEqual(client.get(delete_url).status_code, 200)
        self.assertTrue(PublicReview.objects.filter(pk=self.review.pk).exists())
        token = client.cookies["csrftoken"].value
        for visibility in ("show", "hide"):
            self.assertEqual(client.post(self.url, self.moderation_data(visibility) | {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(client.post(delete_url, {"post": "yes", "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())

    def test_stale_show_and_other_staff_revision_cannot_overwrite_latest_visibility(self):
        for url, payload in ((self.url, self.moderation_data), (self.list_url, self.list_data)):
            stale = payload("show")
            self.patient_edit()
            self.assertEqual(self.client.post(self.url, self.moderation_data("hide")).status_code, 302)
            self.assertContains(self.client.post(url, stale), "This review changed after you opened it.")
            self.review.refresh_from_db()
            self.assertFalse(self.review.is_approved_for_publication)
            self.assertEqual(self.review.body, "New patient-authored text.")

    def test_legacy_checkbox_and_missing_visibility_posts_fail_closed(self):
        for value in ("on", "deactivate", ""):
            response = self.client.post(self.url, self.moderation_data() | {"is_approved_for_publication": value})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
            self.review.refresh_from_db()
            self.assertFalse(self.review.is_approved_for_publication)
