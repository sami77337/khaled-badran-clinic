import re
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from .models import PublicReview
from .showcase import review_source_summary


class ReviewModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username="synthetic-moderator", is_staff=True)
        cls.staff.user_permissions.set(Permission.objects.filter(
            content_type__app_label="core",
            codename__in=("view_publicreview", "change_publicreview", "delete_publicreview"),
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
        self.delete_url = reverse("admin:core_publicreview_delete", args=[self.review.pk])

    def moderation_data(self, action="show", url=None):
        response = self.client.get(url or self.url)
        self.assertEqual(response.status_code, 200)
        form = response.context["adminform"].form
        return {"review_version": form["review_version"].value(), "moderation_action": action}

    def snapshot(self):
        return PublicReview.objects.filter(pk=self.review.pk).values().get()

    def assert_public(self, visible, *, body=None, rating=4):
        summary = {"average_rating": f"{rating:.2f}", "review_count": 1} if visible else None
        self.assertEqual(review_source_summary(), summary)
        for route in ("home", "home_en", "reviews", "reviews_en"):
            response = self.client.get(reverse(route))
            check = self.assertContains if visible else self.assertNotContains
            check(response, body or self.review.body)
            check(response, f'<strong dir="ltr">{rating:.2f}</strong>', html=True)
            if route.startswith("reviews"):
                self.assertEqual(response.context["review_summary"], summary)

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

    def test_patient_detail_renders_revision_and_only_localized_moderation_actions(self):
        for language, hide, show, delete in (("ar", "إخفاء", "إظهار", "حذف"), ("en", "Hide", "Show", "Delete")):
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            for visible in (False, True):
                PublicReview.objects.filter(pk=self.review.pk).update(is_approved_for_publication=visible)
                response = self.client.get(self.url)
                form = response.context["adminform"].form
                self.assertEqual(set(form.fields), {"review_version"})
                self.assertContains(response, 'name="review_version"')
                action = "hide" if visible else "show"
                label = hide if visible else show
                self.assertContains(response, f'value="{action}" class="button default">{label}</button>')
                self.assertContains(response, f'class="deletelink">{delete}</a>')
                for name in ("is_approved_for_publication", "is_active", "is_featured", "display_order",
                             "reviewer_name", "rating", "body", "source", "language", "submitted_by",
                             "_save", "_continue", "_addanother"):
                    self.assertNotContains(response, f'name="{name}"')
                for field in ("is_active", "is_featured", "display_order", "is_approved_for_publication"):
                    self.assertNotContains(response, f'field-{field}')

    def test_mixed_list_hides_patient_controls_and_preserves_imported_controls(self):
        imported = PublicReview.objects.create(reviewer_name="Imported", body="Imported text", language="en", rating=5)
        response = self.client.get(self.list_url)
        forms = {form.instance.pk: form for form in response.context["cl"].formset}
        self.assertEqual(set(forms[self.review.pk].fields), {"id"})
        self.assertEqual(set(forms[imported.pk].fields), {
            "id", "review_version", "is_approved_for_publication", "is_active", "is_featured", "display_order",
        })
        rows = re.findall(r"<tr\b[^>]*>.*?</tr>", response.content.decode(), re.S)
        patient_row = next(row for row in rows if f'href="{self.url}"' in row)
        self.assertIn('class="field-publication_status"', patient_row)
        for field in ("is_approved_for_publication", "is_active", "is_featured", "display_order"):
            self.assertNotIn(field, patient_row)
            self.assertContains(response, f'name="{forms[imported.pk].prefix}-{field}"')

    def test_hide_show_change_every_public_surface_and_aggregate(self):
        for action in ("show", "hide", "show"):
            self.assertEqual(self.client.post(self.url, self.moderation_data(action)).status_code, 302)
            self.assert_public(action == "show")

    def test_show_restores_legacy_inactive_review(self):
        for approved in (False, True):
            PublicReview.objects.filter(pk=self.review.pk).update(is_active=False, is_approved_for_publication=approved)
            self.assertContains(self.client.get(self.url), 'value="show"')
            self.assertEqual(self.client.post(self.url, self.moderation_data()).status_code, 302)
            self.review.refresh_from_db()
            self.assertTrue(self.review.is_active)
            self.assertTrue(self.review.is_approved_for_publication)
            self.assert_public(True)

    def test_crafted_detail_posts_cannot_rewrite_content_or_technical_fields(self):
        PublicReview.objects.filter(pk=self.review.pk).update(is_featured=True, display_order=23)
        for action in ("show", "hide"):
            before = self.snapshot()
            data = self.moderation_data(action) | {
                "body": "Staff rewrite", "rating": 5, "reviewer_name": "Staff rewrite",
                "submitted_by": self.staff.pk, "source": "google", "language": "ar",
                "source_reference": "Forged reference", "reviewed_at": "2000-01-01",
                "is_active": "", "is_featured": "", "display_order": 900,
                "is_approved_for_publication": "on" if action == "hide" else "",
            }
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
            after = self.snapshot()
            self.assertEqual(after["is_approved_for_publication"], action == "show")
            for key in before.keys() - {"is_approved_for_publication", "updated_at"}:
                self.assertEqual(after[key], before[key], key)

    def test_crafted_inline_post_cannot_change_patient_row(self):
        response = self.client.get(self.list_url)
        formset = response.context["cl"].formset
        form = formset.forms[0]
        data = {
            f"{formset.prefix}-TOTAL_FORMS": 1, f"{formset.prefix}-INITIAL_FORMS": 1,
            f"{form.prefix}-id": self.review.pk, f"{form.prefix}-is_approved_for_publication": "on",
            f"{form.prefix}-is_active": "", f"{form.prefix}-is_featured": "on",
            f"{form.prefix}-display_order": 900, f"{form.prefix}-body": "Forged",
            f"{form.prefix}-moderation_action": "show", "_save": "Save",
        }
        before = self.snapshot()
        self.assertEqual(self.client.post(self.list_url, data).status_code, 302)
        self.assertEqual(self.snapshot(), before)

    def test_stale_hide_and_show_after_patient_edit_require_reload(self):
        for action in ("hide", "show"):
            stale = self.moderation_data(action)
            self.patient_edit()
            before = self.snapshot()
            response = self.client.post(self.url, stale)
            self.assertContains(response, "This review changed after you opened it.")
            self.assertEqual(self.snapshot(), before)
            # Resubmitting the error page also retains the stale signed revision.
            stale["review_version"] = response.context["adminform"].form["review_version"].value()
            self.assertContains(self.client.post(self.url, stale), "This review changed after you opened it.")
            self.assertEqual(self.client.post(self.url, self.moderation_data(action)).status_code, 302)
            self.review.refresh_from_db()
            self.assertEqual(self.review.is_approved_for_publication, action == "show")
            self.assertEqual(self.review.body, "New patient-authored text.")

    def test_stale_staff_action_does_not_overwrite_later_moderation(self):
        stale = self.moderation_data("show")
        self.assertEqual(self.client.post(self.url, self.moderation_data("hide")).status_code, 302)
        before = self.snapshot()
        self.assertContains(self.client.post(self.url, stale), "This review changed after you opened it.")
        self.assertEqual(self.snapshot(), before)

    def test_missing_tampered_and_foreign_revision_fail_closed(self):
        other = PublicReview.objects.create(body="Other synthetic review", language="en", rating=5)
        foreign = self.moderation_data(url=reverse("admin:core_publicreview_change", args=[other.pk]))
        for token in ("", "forged-revision", foreign["review_version"]):
            before = self.snapshot()
            response = self.client.post(self.url, self.moderation_data() | {"review_version": token})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
            self.assertEqual(self.snapshot(), before)

    def test_missing_invalid_and_legacy_checkbox_actions_fail_closed(self):
        for action in (None, "", "approve", "deactivate", "delete", "on"):
            data = self.moderation_data(action) | {"is_approved_for_publication": "on", "is_active": "on"}
            if action is None:
                data.pop("moderation_action")
            before = self.snapshot()
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["adminform"].form.errors)
            self.assertEqual(self.snapshot(), before)

    def test_patient_edit_after_hide_republishes_and_owner_can_still_delete(self):
        self.assertEqual(self.client.post(self.url, self.moderation_data("hide")).status_code, 302)
        self.assert_public(False)
        self.patient_edit()
        self.assert_public(True, body="New patient-authored text.", rating=2)
        self.client.force_login(self.patient)
        url = reverse("patient_portal_review_delete_en", args=[self.review.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assert_public(False, body="New patient-authored text.", rating=2)

    def test_get_actions_have_no_side_effects(self):
        before = self.snapshot()
        for url, data in ((self.url, {"moderation_action": "hide"}),
                          (self.url, {"moderation_action": "show"}),
                          (self.delete_url, {"post": "yes"}),
                          (self.list_url, {"action": "delete_selected", "_selected_action": self.review.pk, "post": "yes"})):
            # Django redirects unsupported changelist query parameters to ?e=1.
            self.assertEqual(self.client.get(url, data).status_code, 302 if url == self.list_url else 200)
            self.assertEqual(self.snapshot(), before)

    def test_staff_delete_is_confirmed_and_permanent(self):
        self.assertEqual(self.client.post(self.url, self.moderation_data()).status_code, 302)
        self.assertEqual(self.client.get(self.delete_url).status_code, 200)
        for data in ({"post": "no"}, {"unrelated": "value"}):
            self.assertEqual(self.client.post(self.delete_url, data).status_code, 403)
            self.assertTrue(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assertEqual(self.client.post(self.delete_url, {"post": "yes"}).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assert_public(False)

    def test_bulk_delete_is_confirmed_and_permanent(self):
        data = {"action": "delete_selected", "_selected_action": self.review.pk}
        self.assertEqual(self.client.post(self.list_url, data).status_code, 200)
        self.assertTrue(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assertEqual(self.client.post(self.list_url, data | {"post": "no"}).status_code, 403)
        self.assertTrue(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assertEqual(self.client.post(self.list_url, data | {"post": "yes"}).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())

    def test_change_permission_does_not_grant_delete(self):
        self.staff.user_permissions.remove(Permission.objects.get(
            content_type__app_label="core", codename="delete_publicreview",
        ))
        self.assertEqual(self.client.post(self.url, self.moderation_data()).status_code, 302)
        self.assertNotContains(self.client.get(self.url), 'class="deletelink"')
        self.assertEqual(self.client.post(self.delete_url, {"post": "yes"}).status_code, 403)
        self.assertNotContains(self.client.get(self.list_url), 'value="delete_selected"')
        self.assertTrue(PublicReview.objects.filter(pk=self.review.pk).exists())

    def test_view_only_staff_cannot_moderate_or_delete(self):
        data = self.moderation_data()
        self.staff.user_permissions.set(Permission.objects.filter(
            content_type__app_label="core", codename="view_publicreview",
        ))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="moderation_action"')
        self.assertNotContains(response, 'class="deletelink"')
        before = self.snapshot()
        for url, payload in ((self.url, data), (self.delete_url, {"post": "yes"}),
                             (self.list_url, {"_save": "Save"})):
            self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.client.post(self.list_url, {"action": "delete_selected", "_selected_action": self.review.pk, "post": "yes"})
        self.assertEqual(self.snapshot(), before)

    def test_delete_permission_does_not_grant_hide_or_show(self):
        data = self.moderation_data()
        self.staff.user_permissions.remove(Permission.objects.get(
            content_type__app_label="core", codename="change_publicreview",
        ))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="moderation_action"')
        self.assertContains(response, 'class="deletelink"')
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
        self.assertEqual(self.client.post(self.delete_url, {"post": "yes"}).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())

    def test_nonstaff_and_anonymous_requests_cannot_moderate_or_delete(self):
        data = self.moderation_data()
        before = self.snapshot()
        for user in (self.patient, None):
            if user:
                self.client.force_login(user)
            else:
                self.client.logout()
            for url, payload in ((self.url, data), (self.delete_url, {"post": "yes"})):
                self.assertEqual(self.client.post(url, payload).status_code, 302)
            self.assertEqual(self.snapshot(), before)

    def test_all_moderation_posts_require_csrf_and_valid_tokens_succeed(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        before = self.snapshot()
        for action in ("show", "hide"):
            self.assertEqual(client.post(self.url, self.moderation_data(action)).status_code, 403)
        for url, payload in ((self.delete_url, {"post": "yes"}), (self.list_url, {
            "action": "delete_selected", "_selected_action": self.review.pk, "post": "yes",
        })):
            self.assertEqual(client.post(url, payload).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        for action in ("show", "hide"):
            data = self.moderation_data(action) | {"csrfmiddlewaretoken": token}
            self.assertEqual(client.post(self.url, data).status_code, 302)
        self.assertEqual(client.post(self.delete_url, {"post": "yes", "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())


class ImportedReviewModerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_superuser(username="synthetic-import-moderator")

    def setUp(self):
        self.client.force_login(self.staff)
        self.review = PublicReview.objects.create(reviewer_name="Imported", body="Imported text", language="en", rating=5)
        self.url = reverse("admin:core_publicreview_change", args=[self.review.pk])
        self.list_url = reverse("admin:core_publicreview_changelist")

    def detail_data(self):
        form = self.client.get(self.url).context["adminform"].form
        self.assertEqual(set(form.fields), {
            "review_version", "is_approved_for_publication", "is_active", "is_featured", "display_order",
        })
        return {"review_version": form["review_version"].value(), "is_approved_for_publication": "on",
                "is_active": "on", "is_featured": "on", "display_order": 2, "_save": "Save"}

    def list_data(self):
        formset = self.client.get(self.list_url).context["cl"].formset
        data = {f"{formset.prefix}-TOTAL_FORMS": len(formset.forms),
                f"{formset.prefix}-INITIAL_FORMS": len(formset.forms), "_save": "Save"}
        for form in formset:
            data[f"{form.prefix}-id"] = form.instance.pk
            if form.instance.source != PublicReview.Source.PATIENT_PORTAL:
                data.update({f"{form.prefix}-review_version": form["review_version"].value(),
                             f"{form.prefix}-is_approved_for_publication": "on", f"{form.prefix}-is_active": "on",
                             f"{form.prefix}-is_featured": "on", f"{form.prefix}-display_order": 2})
        return data

    def test_google_and_other_keep_detail_controls_and_saves(self):
        for source in (PublicReview.Source.GOOGLE, PublicReview.Source.OTHER):
            self.review.source = source
            self.review.save()
            self.assertNotContains(self.client.get(self.url), 'name="moderation_action"')
            self.assertEqual(self.client.post(self.url, self.detail_data() | {"body": "Forged"}).status_code, 302)
            self.review.refresh_from_db()
            self.assertTrue(self.review.is_approved_for_publication and self.review.is_active and self.review.is_featured)
            self.assertEqual(self.review.display_order, 2)
            self.assertEqual(self.review.body, "Imported text")
            data = self.detail_data()
            data.pop("is_active")
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
            self.review.refresh_from_db()
            self.assertFalse(self.review.is_active)

    def test_google_and_other_inline_controls_save_with_patient_row_present(self):
        patient = PublicReview.objects.create(source=PublicReview.Source.PATIENT_PORTAL, body="Patient text", language="en", rating=4)
        for source in (PublicReview.Source.GOOGLE, PublicReview.Source.OTHER):
            self.review.source = source
            self.review.is_featured = self.review.is_approved_for_publication = False
            self.review.save()
            self.assertEqual(self.client.post(self.list_url, self.list_data()).status_code, 302)
            self.review.refresh_from_db()
            patient.refresh_from_db()
            self.assertTrue(self.review.is_featured and self.review.is_approved_for_publication and self.review.is_active)
            self.assertEqual(self.review.display_order, 2)
            self.assertFalse(patient.is_approved_for_publication)
            self.assertEqual(patient.body, "Patient text")
            updated_at = self.review.updated_at
            with patch("django.core.signing.time.time", return_value=1):
                unchanged = self.list_data()
            self.assertEqual(self.client.post(self.list_url, unchanged).status_code, 302)
            self.review.refresh_from_db()
            self.assertEqual(self.review.updated_at, updated_at)

    def test_imported_stale_detail_and_inline_saves_remain_rejected(self):
        for url, payload in ((self.url, self.detail_data), (self.list_url, self.list_data)):
            data = payload()
            self.review.body += " New imported revision."
            self.review.save()
            self.assertContains(self.client.post(url, data), "This review changed after you opened it.")
            self.review.refresh_from_db()
            self.assertFalse(self.review.is_approved_for_publication)
            self.assertTrue(self.review.body.endswith("New imported revision."))
