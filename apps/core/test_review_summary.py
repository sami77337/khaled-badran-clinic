"""Published website aggregates and external rating-only imports; no real data in Git."""
from collections import Counter
from io import StringIO
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import reverse

from .models import PublicReview
from .showcase import approved_reviews, review_source_summary


class PublishedReviewSummaryTests(TestCase):
    def create_review(self, **changes):
        return PublicReview.objects.create(**{
            "reviewer_name": "Synthetic reviewer", "body": "Synthetic feedback.",
            "rating": 5, "language": "en", "source": PublicReview.Source.GOOGLE,
            "is_approved_for_publication": True, "is_active": True, **changes,
        })

    def test_average_count_and_public_list_include_only_approved_active_rows(self):
        five = self.create_review(rating=5)
        four = self.create_review(rating=4, body="", language="ar")
        self.create_review(rating=1, is_approved_for_publication=False)
        self.create_review(rating=2, is_active=False)
        self.create_review(rating=3, is_active=False, is_approved_for_publication=False)
        with self.assertNumQueries(1):
            self.assertEqual(review_source_summary(), {"average_rating": "4.50", "review_count": 2})
        self.assertEqual({r.pk for r in approved_reviews()}, {five.pk, four.pk})

    def test_all_sources_languages_and_rating_only_external_rows_contribute(self):
        self.create_review(rating=5, body="", language="ar")
        self.create_review(rating=4, source=PublicReview.Source.PATIENT_PORTAL)
        self.create_review(rating=3, body="", source=PublicReview.Source.OTHER)
        self.assertEqual(review_source_summary(), {"average_rating": "4.00", "review_count": 3})
        self.assertEqual(len(approved_reviews()), 3)

    def test_summary_is_not_limited_by_language_filter_or_home_card_limit(self):
        for _ in range(12):
            self.create_review(language="ar")
        self.create_review(rating=1, language="en")
        response = self.client.get(reverse("reviews_en"), {"filter": "en"})
        self.assertEqual(len(response.context["reviews"]), 1)
        self.assertEqual(response.context["review_summary"], {"average_rating": "4.69", "review_count": 13})
        home = self.client.get(reverse("home_en"))
        self.assertContains(home, '<strong dir="ltr">4.69</strong>', html=True)
        self.assertContains(home, "13 published reviews")
        self.assertEqual(len(approved_reviews(limit=12)), 12)

    def test_status_changes_and_deletion_recalculate_without_stale_cache(self):
        self.create_review(rating=5)
        review = self.create_review(rating=4, is_approved_for_publication=False)
        for approved, active, average, count in (
            (False, True, "5.00", 1), (True, True, "4.50", 2),
            (False, True, "5.00", 1), (True, False, "5.00", 1),
            (True, True, "4.50", 2), (False, False, "5.00", 1),
        ):
            with self.subTest(approved=approved, active=active):
                review.is_approved_for_publication = approved
                review.is_active = active
                review.save()
                response = self.client.get(reverse("reviews_en"))
                self.assertEqual(response.context["review_summary"], {
                    "average_rating": average, "review_count": count,
                })
        review.is_approved_for_publication = review.is_active = True
        review.save()
        self.assertEqual(review_source_summary()["review_count"], 2)
        review.delete()
        self.assertEqual(review_source_summary(), {"average_rating": "5.00", "review_count": 1})

    def test_patient_submission_edit_and_delete_immediately_change_aggregate(self):
        owner = get_user_model().objects.create_user(username="synthetic-summary-patient")
        moderator = get_user_model().objects.create_superuser(username="synthetic-summary-moderator")
        self.client.force_login(owner)
        response = self.client.post(reverse("patient_portal_review_en"), {"rating": 4, "body": "My feedback."})
        self.assertEqual(response.status_code, 302)
        review = PublicReview.objects.get(submitted_by=owner)
        self.assertEqual(review_source_summary(), {"average_rating": "4.00", "review_count": 1})

        self.client.force_login(moderator)
        moderation_url = reverse("admin:core_publicreview_change", args=[review.pk])
        form = self.client.get(moderation_url).context["adminform"].form
        response = self.client.post(moderation_url, {
            "review_version": form["review_version"].value(), "is_approved_for_publication": "on",
            "is_active": "on", "is_featured": "on", "display_order": 0, "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(review_source_summary(), {"average_rating": "4.00", "review_count": 1})

        self.client.force_login(owner)
        response = self.client.post(reverse("patient_portal_review_edit_en", args=[review.pk]), {
            "rating": 5, "body": "Edited patient feedback.",
        })
        self.assertEqual(response.status_code, 302)
        review.refresh_from_db()
        self.assertTrue(review.is_approved_for_publication)
        self.assertFalse(review.is_featured)
        self.assertEqual(review_source_summary(), {"average_rating": "5.00", "review_count": 1})
        response = self.client.post(reverse("patient_portal_review_delete_en", args=[review.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(review_source_summary())

    def test_patient_blank_body_still_rejected_in_both_languages(self):
        owner = get_user_model().objects.create_user(username="synthetic-blank-review-patient")
        self.client.force_login(owner)
        for suffix in ("", "_en"):
            for body in ("", " \n "):
                with self.subTest(suffix=suffix, body=body):
                    response = self.client.post(reverse("patient_portal_review" + suffix), {
                        "rating": 5, "body": body, "source": "google",
                    })
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("body", response.context["form"].errors)
                    self.assertFalse(PublicReview.objects.exists())

    def test_rating_only_cards_have_name_stars_source_and_no_quote_or_images(self):
        self.create_review(reviewer_name="Rating only reviewer", rating=4, body="")
        self.create_review(reviewer_name="Whitespace reviewer", rating=5, body=" \n ")
        for route in ("home", "home_en", "reviews", "reviews_en"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                cards = re.findall(r'<article class="home-review-card\b.*?</article>', response.content.decode(), re.S)
                self.assertEqual(len(cards), 2)
                self.assertContains(response, "Rating only reviewer")
                self.assertContains(response, 'aria-label="4 / 5"')
                self.assertContains(response, "★★★★☆")
                for card in cards:
                    self.assertIn("review-card-rating-only", card)
                    self.assertIn("<span>Google</span>", card)
                    self.assertNotIn("<blockquote", card)
                    self.assertNotRegex(card, r"<(img|picture|svg|video)\b")

    def test_empty_summary_is_safe_and_localized(self):
        self.create_review(is_approved_for_publication=False)
        self.create_review(is_active=False)
        self.assertIsNone(review_source_summary())
        for route in ("home", "home_en", "reviews", "reviews_en"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'class="home-review-summary')
                if route.startswith("reviews"):
                    self.assertContains(response, "No approved reviews" if route.endswith("_en") else "لا توجد آراء معتمدة")


class ExternalReviewImportTests(TestCase):
    def import_path(self, path):
        output = StringIO()
        call_command("import_public_reviews", str(path), approve=True, stdout=output)
        return output.getvalue()

    def assert_approved_dataset(self, path):
        self.assertIn("57 created, 0 updated", self.import_path(path))
        original_ids = set(PublicReview.objects.values_list("pk", flat=True))
        self.assertIn("0 created, 57 updated", self.import_path(path))
        self.assertEqual(set(PublicReview.objects.values_list("pk", flat=True)), original_ids)
        reviews = PublicReview.objects.all()
        self.assertEqual(reviews.count(), 57)
        self.assertEqual(reviews.exclude(body="").count(), 40)
        self.assertEqual(reviews.filter(body="").count(), 17)
        self.assertEqual(Counter(reviews.values_list("rating", flat=True)), {5: 53, 4: 4})
        self.assertEqual(sum(reviews.values_list("rating", flat=True)), 281)
        self.assertEqual(reviews.filter(
            source=PublicReview.Source.GOOGLE, is_active=True, is_approved_for_publication=True,
            reviewed_at__isnull=True, source_reference="", submitted_by__isnull=True,
        ).count(), 57)
        self.assertEqual(review_source_summary(), {"average_rating": "4.93", "review_count": 57})
        for route, label, count_text, denominator in (
            ("reviews", "متوسط التقييم", "من 57 تقييمًا منشورًا", "من 5"),
            ("reviews_en", "Average Rating", "Across 57 published reviews", "out of 5"),
        ):
            response = self.client.get(reverse(route))
            self.assertContains(response, '<strong dir="ltr">4.93</strong>', html=True)
            for text in (label, count_text, denominator, "★★★★★"):
                self.assertContains(response, text)
            cards = re.findall(r'<article class="home-review-card\b.*?</article>', response.content.decode(), re.S)
            self.assertEqual(len(cards), 57)
            self.assertEqual(sum("<blockquote>" in card for card in cards), 40)
            self.assertEqual(sum("review-card-rating-only" in card for card in cards), 17)
            self.assertFalse(any(re.search(r"<(img|picture|svg|video)\b", card) for card in cards))

    def test_synthetic_external_dataset_imports_once_with_expected_aggregate(self):
        # Match the approved distribution using entirely synthetic names/text.
        rows = [{
            "reviewer_name": f"Synthetic import reviewer {index}",
            "body": f"Synthetic review {index}." if index < 40 else "",
            "rating": 5 if index < 53 else 4, "language": "ar" if index % 2 else "en",
            "source": "google",
        } for index in range(57)]
        with TemporaryDirectory(prefix="kbc-synthetic-reviews-") as directory:
            path = Path(directory) / "reviews.json"
            path.write_text(json.dumps({"reviews": rows}), encoding="utf-8")
            self.assert_approved_dataset(path)

    def test_owner_approved_external_file_when_explicitly_supplied(self):
        external_path = os.environ.get("KBC_OWNER_APPROVED_REVIEWS_JSON")
        if not external_path:
            self.skipTest("Set KBC_OWNER_APPROVED_REVIEWS_JSON to verify owner data directly outside Git")
        path = Path(external_path)
        self.assertTrue(path.is_absolute())
        self.assertFalse(path.resolve().is_relative_to(settings.BASE_DIR.resolve()))
        self.assert_approved_dataset(path)

    def test_external_import_cannot_create_patient_portal_reviews(self):
        with TemporaryDirectory(prefix="kbc-synthetic-reviews-") as directory:
            path = Path(directory) / "reviews.json"
            path.write_text(json.dumps([{
                "reviewer_name": "Synthetic forbidden source", "rating": 5,
                "body": "", "language": "en", "source": "patient_portal",
            }]), encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "unsupported source"):
                self.import_path(path)
            self.assertFalse(PublicReview.objects.exists())

    def test_invalid_rating_only_row_rolls_back_entire_import(self):
        with TemporaryDirectory(prefix="kbc-synthetic-reviews-") as directory:
            path = Path(directory) / "reviews.json"
            path.write_text(json.dumps([
                {"reviewer_name": "Valid synthetic", "rating": 5, "body": "", "language": "en"},
                {"reviewer_name": "Invalid synthetic", "rating": 6, "body": "", "language": "en"},
            ]), encoding="utf-8")
            with self.assertRaises(ValidationError):
                self.import_path(path)
            self.assertFalse(PublicReview.objects.exists())
