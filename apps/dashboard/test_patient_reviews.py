from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import AuditLog, PublicReview
from apps.core.showcase import review_source_summary


class DashboardPatientReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.moderator = get_user_model().objects.create_user(username="synthetic-dashboard-moderator", is_staff=True)
        cls.moderator.user_permissions.set(Permission.objects.filter(
            content_type__app_label="core", codename__in=("view_publicreview", "change_publicreview", "delete_publicreview"),
        ))
        cls.patient = get_user_model().objects.create_user(username="synthetic-patient-account-private")

    def setUp(self):
        self.client.force_login(self.moderator)
        self.review = PublicReview.objects.create(
            submitted_by=self.patient, source=PublicReview.Source.PATIENT_PORTAL,
            reviewer_name="Synthetic display name", body="Synthetic patient feedback.",
            rating=4, language="en", is_approved_for_publication=True,
        )
        self.list_url = reverse("dashboard_patient_reviews") + "?lang=en"
        self.visibility_url = reverse("dashboard_patient_review_visibility", args=[self.review.pk]) + "?lang=en"
        self.delete_url = reverse("dashboard_patient_review_delete", args=[self.review.pk]) + "?lang=en"

    def action_data(self, *, review_id=None):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        item = next(item for item in response.context["review_items"] if item["review"].pk == (review_id or self.review.pk))
        return {"review_version": item["form"]["review_version"].value(), "moderation_action": item["action"]}

    def delete_data(self):
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        return {"review_version": response.context["form"]["review_version"].value(), "post": "yes"}

    def snapshot(self):
        return PublicReview.objects.filter(pk=self.review.pk).values().get()

    def assert_public(self, visible, *, body=None, rating=4):
        summary = {"average_rating": f"{rating:.2f}", "review_count": 1} if visible else None
        self.assertEqual(review_source_summary(), summary)
        for route in ("home", "home_en", "reviews", "reviews_en"):
            response = self.client.get(reverse(route))
            (self.assertContains if visible else self.assertNotContains)(response, body or self.review.body)

    def test_localized_list_and_navigation_use_dashboard_without_technical_controls(self):
        for language, title, hide, delete in (("ar", "تقييمات المرضى", "إخفاء", "حذف"), ("en", "Patient Reviews", "Hide", "Delete")):
            response = self.client.get(reverse("dashboard_patient_reviews"), {"lang": language})
            self.assertContains(response, title)
            self.assertContains(response, hide)
            self.assertContains(response, delete)
            self.assertContains(response, 'aria-current="page"')
            self.assertContains(response, 'dir="rtl"' if language == "ar" else 'dir="ltr"')
            self.assertContains(response, 'name="robots" content="noindex,nofollow"')
            self.assertIn("no-store", response["Cache-Control"])
            self.assertContains(response, self.review.body)
            self.assertNotContains(response, self.patient.username)
            for name in ("body", "rating", "reviewer_name", "submitted_by", "source", "is_active", "is_featured", "display_order", "is_approved_for_publication"):
                self.assertNotContains(response, f'name="{name}"')

    def test_imported_reviews_are_excluded_and_cannot_be_targeted(self):
        for source in (PublicReview.Source.GOOGLE, PublicReview.Source.OTHER):
            imported = PublicReview.objects.create(source=source, body="Synthetic imported feedback", language="en", rating=5)
            before = PublicReview.objects.filter(pk=imported.pk).values().get()
            self.assertNotContains(self.client.get(self.list_url), imported.body)
            for route in ("dashboard_patient_review_visibility", "dashboard_patient_review_delete"):
                url = reverse(route, args=[imported.pk])
                self.assertEqual(self.client.post(url, self.action_data() | {"post": "yes"}).status_code, 404)
                if route.endswith("delete"):
                    self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(PublicReview.objects.filter(pk=imported.pk).values().get(), before)

    def test_hide_show_update_public_surfaces_and_aggregates(self):
        for action in ("hide", "show", "hide", "show"):
            data = self.action_data()
            self.assertEqual(data["moderation_action"], action)
            response = self.client.post(self.visibility_url, data)
            self.assertRedirects(response, self.list_url, fetch_redirect_response=False)
            self.assert_public(action == "show")

    def test_show_restores_legacy_inactive_patient_review(self):
        self.review.is_active = False
        self.review.save()
        data = self.action_data()
        self.assertEqual(data["moderation_action"], "show")
        self.assertEqual(self.client.post(self.visibility_url, data).status_code, 302)
        self.assert_public(True)

    def test_forged_content_and_technical_fields_never_change(self):
        self.review.is_featured = True
        self.review.display_order = 42
        self.review.save()
        for unused in range(2):
            before = self.snapshot()
            data = self.action_data() | {
                "reviewer_name": "Forged name", "rating": 1, "body": "Forged body",
                "language": "ar", "source": "google", "submitted_by": self.moderator.pk,
                "is_active": "", "is_featured": "", "display_order": 1,
                "is_approved_for_publication": "", "reviewed_at": "2000-01-01",
            }
            self.assertEqual(self.client.post(self.visibility_url, data).status_code, 302)
            after = self.snapshot()
            for key in before.keys() - {"is_approved_for_publication", "updated_at"}:
                self.assertEqual(after[key], before[key], key)

    def test_patient_edit_republishes_and_invalidates_visibility_and_delete_forms(self):
        self.assertEqual(self.client.post(self.visibility_url, self.action_data()).status_code, 302)
        stale_visibility = self.action_data()
        stale_delete = self.delete_data()
        self.client.force_login(self.patient)
        response = self.client.post(reverse("patient_portal_review_edit_en", args=[self.review.pk]), {
            "reviewer_name": "Updated patient display", "rating": 2, "body": "Updated synthetic feedback.",
        })
        self.assertEqual(response.status_code, 302)
        self.assert_public(True, body="Updated synthetic feedback.", rating=2)
        self.client.force_login(self.moderator)
        before = self.snapshot()
        for url, data in ((self.visibility_url, stale_visibility), (self.delete_url, stale_delete)):
            response = self.client.post(url, data)
            self.assertEqual(response.status_code, 400)
            self.assertContains(response, "Reload the review", status_code=400)
            self.assertNotContains(response, 'name="review_version"', status_code=400)
            self.assertEqual(self.snapshot(), before)

    def test_admin_moderation_invalidates_dashboard_forms(self):
        stale = self.action_data()
        stale_delete = self.delete_data()
        url = reverse("admin:core_publicreview_change", args=[self.review.pk])
        form = self.client.get(url).context["adminform"].form
        self.assertEqual(self.client.post(url, {
            "review_version": form["review_version"].value(), "moderation_action": "hide",
        }).status_code, 302)
        before = self.snapshot()
        self.assertEqual(self.client.post(self.visibility_url, stale).status_code, 400)
        self.assertEqual(self.client.post(self.delete_url, stale_delete).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_replayed_visibility_form_is_rejected(self):
        data = self.action_data()
        self.assertEqual(self.client.post(self.visibility_url, data).status_code, 302)
        before = self.snapshot()
        self.assertEqual(self.client.post(self.visibility_url, data).status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_audit_records_actor_and_action_without_patient_content(self):
        for unused in range(2):
            self.assertEqual(self.client.post(self.visibility_url, self.action_data()).status_code, 302)
        self.assertEqual(self.client.post(self.delete_url, self.delete_data()).status_code, 302)
        entries = list(AuditLog.objects.filter(model_name="PublicReview").order_by("created_at"))
        self.assertEqual([entry.metadata for entry in entries], [
            {"action": "patient_review_hide"}, {"action": "patient_review_show"}, {"action": "patient_review_delete"},
        ])
        for entry in entries:
            self.assertEqual(entry.user_id, self.moderator.pk)
            self.assertEqual(entry.object_id, str(self.review.pk))
            self.assertEqual(entry.object_repr, "")
            self.assertEqual(entry.message, "")

    def test_missing_tampered_foreign_and_wrong_action_tokens_fail_closed(self):
        other = PublicReview.objects.create(source=PublicReview.Source.PATIENT_PORTAL, body="Other synthetic review", rating=5, language="en")
        valid = self.action_data()
        for data in (
            {}, valid | {"review_version": ""}, valid | {"review_version": "tampered"},
            valid | {"review_version": self.action_data(review_id=other.pk)["review_version"]},
            valid | {"moderation_action": "show"}, valid | {"moderation_action": "delete"},
            valid | {"moderation_action": "approve"}, valid | {"moderation_action": ""},
        ):
            before = self.snapshot()
            self.assertEqual(self.client.post(self.visibility_url, data).status_code, 400)
            self.assertEqual(self.snapshot(), before)

    def test_delete_requires_confirmation_and_delete_specific_token(self):
        before = self.snapshot()
        data = self.delete_data()
        self.assertEqual(self.snapshot(), before)
        for invalid in ({}, data | {"post": ""}, data | {"post": "no"}, data | {"review_version": "tampered"}, self.action_data() | {"post": "yes"}):
            self.assertEqual(self.client.post(self.delete_url, invalid).status_code, 400)
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.post(self.delete_url, data).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.patient.pk).exists())
        self.assert_public(False)
        self.assertEqual(self.client.post(self.delete_url, data).status_code, 404)

    def test_anonymous_and_patient_requests_cannot_read_or_mutate(self):
        data = self.action_data()
        deletion = self.delete_data()
        before = self.snapshot()
        for patient in (False, True):
            client = Client()
            if patient:
                client.force_login(self.patient)
            for method, url, payload in (("get", self.list_url, {}), ("get", self.delete_url, {}), ("post", self.visibility_url, data), ("post", self.delete_url, deletion)):
                response = getattr(client, method)(url, payload)
                self.assertEqual(response.status_code, 403 if patient else 302)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertNotIn(self.review.body, response.content.decode())
            self.assertEqual(self.snapshot(), before)

    def test_all_staff_can_read_change_and_delete_without_model_permissions(self):
        staff = get_user_model().objects.create_user(
            username="synthetic-clinic-staff-reviewer", is_staff=True
        )
        client = Client()
        client.force_login(staff)

        response = client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="moderation_action"')
        self.assertContains(response, self.delete_url)

        home = client.get(reverse("dashboard_home"))
        self.assertContains(home, reverse("dashboard_patient_reviews"))

        item = next(
            item for item in response.context["review_items"]
            if item["review"].pk == self.review.pk
        )
        visibility_data = {
            "review_version": item["form"]["review_version"].value(),
            "moderation_action": item["action"],
        }
        self.assertEqual(
            client.post(self.visibility_url, visibility_data).status_code,
            302,
        )

        delete_page = client.get(self.delete_url)
        self.assertEqual(delete_page.status_code, 200)
        delete_data = {
            "review_version": delete_page.context["form"]["review_version"].value(),
            "post": "yes",
        }
        self.assertEqual(client.post(self.delete_url, delete_data).status_code, 302)
        self.assertFalse(PublicReview.objects.filter(pk=self.review.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                user=staff,
                metadata__action="patient_review_delete",
            ).exists()
        )

    def test_csrf_is_required_for_visibility_and_delete(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.moderator)
        before = self.snapshot()
        for url, data in ((self.visibility_url, self.action_data()), (self.delete_url, self.delete_data())):
            self.assertEqual(client.post(url, data).status_code, 403)
            self.assertEqual(self.snapshot(), before)
        response = client.get(self.list_url)
        item = response.context["review_items"][0]
        data = {"review_version": item["form"]["review_version"].value(), "moderation_action": "hide", "csrfmiddlewaretoken": client.cookies["csrftoken"].value}
        self.assertEqual(client.post(self.visibility_url, data).status_code, 302)

    def test_gets_are_read_only_and_unsupported_methods_are_rejected(self):
        before = self.snapshot()
        for url in (self.list_url, self.delete_url):
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.put(url).status_code, 405)
        self.assertEqual(self.client.get(self.visibility_url).status_code, 405)
        self.assertEqual(self.client.post(self.list_url).status_code, 405)
        self.assertEqual(self.snapshot(), before)

    def test_deleted_review_cannot_be_moderated_with_an_old_form(self):
        data = self.action_data()
        self.review.delete()
        self.assertEqual(self.client.post(self.visibility_url, data).status_code, 404)

    def test_pagination_is_bounded_localized_and_handles_invalid_pages(self):
        PublicReview.objects.bulk_create([
            PublicReview(source=PublicReview.Source.PATIENT_PORTAL, body=f"Synthetic review {index}", rating=5, language="ar")
            for index in range(24)
        ])
        first = self.client.get(self.list_url)
        self.assertEqual(len(first.context["review_items"]), 20)
        self.assertEqual(first.context["page"].paginator.count, 25)
        self.assertEqual(first.context["next_url"], self.list_url + "&page=2")
        second = self.client.get(first.context["next_url"])
        self.assertEqual(len(second.context["review_items"]), 5)
        self.assertEqual(second.context["dashboard_language_switch_url"], reverse("dashboard_patient_reviews") + "?page=2")
        for value in ("abc", "-1", "99999999999999999999999999999"):
            self.assertEqual(self.client.get(self.list_url + "&page=" + value).status_code, 200)

    def test_empty_state_and_user_text_are_safe(self):
        self.review.reviewer_name = '<script>alert("name")</script>'
        self.review.body = '<img src=x onerror="alert(1)">\nSecond line.'
        self.review.save()
        for url in (self.list_url, self.delete_url):
            response = self.client.get(url)
            self.assertNotContains(response, "<script>alert")
            self.assertNotContains(response, '<img src=x')
            self.assertContains(response, "&lt;img src=x")
            self.assertContains(response, "<br>")
        self.review.delete()
        self.assertContains(self.client.get(self.list_url), "No patient reviews yet.")
