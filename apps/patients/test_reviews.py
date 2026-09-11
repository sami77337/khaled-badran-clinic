from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.html import escape

from apps.core.models import PublicReview


class PatientReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="synthetic-review-owner")
        cls.other = get_user_model().objects.create_user(username="synthetic-review-other")
        cls.staff = get_user_model().objects.create_user(username="synthetic-review-staff", is_staff=True)
        cls.superuser = get_user_model().objects.create_user(username="synthetic-review-admin", is_superuser=True)

    def setUp(self):
        self.client.force_login(self.owner)

    def url(self, action="", language="en", review=None):
        route = "patient_portal_review" + (f"_{action}" if action else "")
        return reverse(route + ("_en" if language == "en" else ""), kwargs={"review_id": review.pk} if review else None)

    def create_review(self, **kwargs):
        defaults = {
            "submitted_by": self.owner, "source": PublicReview.Source.PATIENT_PORTAL,
            "reviewer_name": "", "body": "Synthetic review text.", "rating": 4, "language": "en",
        }
        return PublicReview.objects.create(**(defaults | kwargs))

    def assert_private(self, response):
        for directive in ("no-store", "no-cache", "private"):
            self.assertIn(directive, response.headers["Cache-Control"])

    def test_anonymous_routes_require_localized_login(self):
        review = self.create_review()
        self.client.logout()
        for language in ("ar", "en"):
            for action in ("", "edit", "delete"):
                for method in (self.client.get, self.client.post):
                    with self.subTest(language=language, action=action, method=method.__name__):
                        response = method(self.url(action, language, review if action else None))
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(response.url.startswith("/en/login/?" if language == "en" else "/login/?"))
                        self.assertIn("role=patient", response.url)
                        self.assert_private(response)

    def test_staff_and_superusers_cannot_submit_edit_or_delete(self):
        review = self.create_review()
        for user in (self.staff, self.superuser):
            self.client.force_login(user)
            for language in ("ar", "en"):
                for action in ("", "edit", "delete"):
                    for method in (self.client.get, self.client.post):
                        with self.subTest(user=user.pk, language=language, action=action):
                            response = method(self.url(action, language, review if action else None))
                            self.assertEqual(response.status_code, 403)
                            self.assert_private(response)
        self.assertTrue(PublicReview.objects.filter(pk=review.pk).exists())

    def test_other_patient_cannot_access_or_mutate_review(self):
        review = self.create_review(submitted_by=self.other)
        for language in ("ar", "en"):
            for action in ("edit", "delete"):
                response = self.client.post(self.url(action, language, review), {"rating": 1, "body": "Forged"})
                self.assertEqual(response.status_code, 404)
            self.assertEqual(self.client.get(self.url("edit", language, review)).status_code, 404)
            self.assertNotContains(self.client.get(self.url(language=language)), review.body)
        review.refresh_from_db()
        self.assertEqual(review.body, "Synthetic review text.")

    def test_imported_reviews_are_not_patient_editable_even_with_same_user(self):
        review = self.create_review(source=PublicReview.Source.GOOGLE)
        self.assertEqual(self.client.get(self.url("edit", review=review)).status_code, 404)
        self.assertEqual(self.client.post(self.url("delete", review=review)).status_code, 404)
        response = self.client.post(self.url(), {"rating": 5, "body": "Portal review"})
        self.assertRedirects(response, self.url())
        self.assertEqual(PublicReview.objects.filter(submitted_by=self.owner).count(), 2)

    def test_submission_binds_owner_and_ignores_forged_moderation_fields(self):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                response = self.client.post(self.url(language=language), {
                    "reviewer_name": "   ", "body": "  Synthetic submitted review.  ", "rating": 5,
                    "submitted_by": self.other.pk, "source": "google", "language": "invalid",
                    "is_approved_for_publication": "on", "is_active": "", "is_featured": "on",
                    "display_order": 900, "source_reference": "private-reference",
                })
                self.assertRedirects(response, self.url(language=language))
                self.assert_private(response)
                review = PublicReview.objects.get(submitted_by=self.owner)
                self.assertEqual(review.source, PublicReview.Source.PATIENT_PORTAL)
                self.assertEqual(review.language, language)
                self.assertEqual(review.body, "Synthetic submitted review.")
                self.assertEqual(review.reviewer_name, "")
                self.assertEqual(review.rating, 5)
                self.assertEqual(review.reviewed_at, timezone.localdate())
                self.assertEqual(review.source_reference, "")
                self.assertEqual(review.display_order, 0)
                self.assertTrue(review.is_active)
                self.assertTrue(review.is_approved_for_publication)
                self.assertFalse(review.is_featured)
                review.delete()

    def test_duplicate_submission_preserves_original_review(self):
        review = self.create_review()
        response = self.client.post(self.url(), {"body": "Replacement", "rating": 1})
        self.assertRedirects(response, self.url())
        review.refresh_from_db()
        self.assertEqual(review.body, "Synthetic review text.")
        self.assertEqual(PublicReview.objects.filter(submitted_by=self.owner).count(), 1)

    def test_database_enforces_one_portal_review_per_user(self):
        self.create_review()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_review()
        self.create_review(submitted_by=self.other)
        self.create_review(submitted_by=None, source=PublicReview.Source.GOOGLE)
        self.create_review(submitted_by=None, source=PublicReview.Source.GOOGLE)

    def test_invalid_submissions_do_not_create_reviews(self):
        for data in ({}, {"rating": 0, "body": "Text"}, {"rating": 6, "body": "Text"},
                     {"rating": "1.5", "body": "Text"}, {"rating": 4, "body": "  "},
                     {"reviewer_name": "x" * 161, "rating": 4, "body": "Text"}):
            with self.subTest(data=data):
                response = self.client.post(self.url(), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertFalse(PublicReview.objects.exists())

    def test_validation_follows_page_language_over_browser_locale(self):
        for language, opposite in (("ar", "en"), ("en", "ar")):
            response = self.client.post(self.url(language=language), {}, HTTP_ACCEPT_LANGUAGE=opposite)
            with translation.override(language):
                self.assertContains(response, escape(translation.gettext("This field is required.")))
            with translation.override(opposite):
                self.assertNotContains(response, escape(translation.gettext("This field is required.")))

    def test_edit_publishes_immediately_and_preserves_owner_and_source(self):
        review = self.create_review(is_approved_for_publication=True, is_featured=True, is_active=False)
        response = self.client.post(self.url("edit", review=review), {
            "reviewer_name": "Updated display", "rating": 2, "body": "Updated patient review.",
            "submitted_by": self.other.pk, "source": "google", "is_approved_for_publication": "on",
        })
        self.assertRedirects(response, self.url())
        review.refresh_from_db()
        self.assertEqual(review.body, "Updated patient review.")
        self.assertEqual(review.rating, 2)
        self.assertEqual(review.submitted_by, self.owner)
        self.assertEqual(review.source, PublicReview.Source.PATIENT_PORTAL)
        self.assertTrue(review.is_approved_for_publication)
        self.assertFalse(review.is_featured)
        self.assertTrue(review.is_active)

    def test_invalid_edit_preserves_content_and_approval(self):
        review = self.create_review(is_approved_for_publication=True)
        response = self.client.post(self.url("edit", review=review), {"body": "", "rating": 0})
        self.assertEqual(response.status_code, 200)
        review.refresh_from_db()
        self.assertEqual(review.body, "Synthetic review text.")
        self.assertTrue(review.is_approved_for_publication)

    def test_delete_is_post_only_and_removes_review_permanently(self):
        review = self.create_review(is_approved_for_publication=True)
        url = self.url("delete", review=review)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(PublicReview.objects.filter(pk=review.pk).exists())
        self.assertRedirects(self.client.post(url), self.url())
        self.assertFalse(PublicReview.objects.filter(pk=review.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertRedirects(self.client.post(self.url(), {"body": "New submission", "rating": 3}), self.url())

    def test_all_mutations_require_csrf(self):
        review = self.create_review()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        for language in ("ar", "en"):
            for action in ("", "edit", "delete"):
                response = client.post(self.url(action, language, review if action else None), {"rating": 5, "body": "Forged"})
                self.assertEqual(response.status_code, 403)
        review.refresh_from_db()
        self.assertEqual(review.body, "Synthetic review text.")

    def test_submission_with_real_csrf_token_succeeds(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        client.get(self.url())
        response = client.post(self.url(), {
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value, "rating": 4, "body": "CSRF verified review",
        })
        self.assertRedirects(response, self.url())

    def test_review_states_are_localized_private_and_linked_from_account(self):
        review = self.create_review()
        for language in ("ar", "en"):
            url = self.url(language=language)
            account = reverse("patient_portal_account" + ("_en" if language == "en" else ""))
            self.assertContains(self.client.get(account), f'href="{url}"')
            for approved, active, status in ((False, True, "hidden"), (True, True, "published"), (True, False, "hidden")):
                PublicReview.objects.filter(pk=review.pk).update(is_approved_for_publication=approved, is_active=active)
                response = self.client.get(url)
                self.assertContains(response, f'data-review-status="{status}"')
                self.assertContains(response, "مريض" if language == "ar" else "Patient")
                self.assertContains(response, 'name="robots" content="noindex,nofollow"')
                self.assert_private(response)
            edit = self.client.get(self.url("edit", language, review))
            self.assertEqual(edit.context["portal_language_switch_url"], self.url("edit", "ar" if language == "en" else "en", review))

    def test_public_display_requires_approval_and_activity_and_never_exposes_owner(self):
        review = self.create_review(body="Synthetic public visibility marker.")
        for approved, active in ((False, True), (True, False), (True, True)):
            PublicReview.objects.filter(pk=review.pk).update(is_approved_for_publication=approved, is_active=active)
            for route in ("home", "home_en", "reviews", "reviews_en"):
                response = self.client.get(reverse(route))
                if approved and active:
                    self.assertContains(response, review.body)
                    self.assertContains(response, "تقييم مريض" if not route.endswith("_en") else "Patient review")
                else:
                    self.assertNotContains(response, review.body)
                self.assertNotContains(response, self.owner.username)

    def test_patient_html_is_escaped_on_portal_and_public_pages(self):
        review = self.create_review(
            reviewer_name='<script>alert("name")</script>', body='<script>alert("body")</script>',
            is_approved_for_publication=True,
        )
        for url in (self.url(), reverse("home"), reverse("home_en"), reverse("reviews"), reverse("reviews_en")):
            response = self.client.get(url)
            self.assertContains(response, escape(review.body))
            self.assertContains(response, escape(review.reviewer_name))
            self.assertNotContains(response, review.body)
            self.assertNotContains(response, review.reviewer_name)
