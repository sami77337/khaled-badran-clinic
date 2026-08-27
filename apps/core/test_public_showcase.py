import json
import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.patients.models import Patient
from apps.records.models import RecordMedia, VisitRecord

from .models import PublicReview, SystemSetting
from .showcase import (
    GOOGLE_REVIEW_AVERAGE_KEY,
    GOOGLE_REVIEW_COUNT_KEY,
    grouped_public_cases,
)


class PublicReviewShowcaseTests(TestCase):
    def setUp(self):
        self.ar_review = PublicReview.objects.create(
            reviewer_name="مراجع عربي",
            body="تجربة ممتازة مع الدكتور خالد.",
            rating=5,
            language=PublicReview.Language.ARABIC,
            is_approved_for_publication=True,
            is_active=True,
            is_featured=True,
        )
        self.en_review = PublicReview.objects.create(
            reviewer_name="English Reviewer",
            body="Excellent experience with Dr. Khaled.",
            rating=5,
            language=PublicReview.Language.ENGLISH,
            is_approved_for_publication=True,
            is_active=True,
        )
        PublicReview.objects.create(
            reviewer_name="Hidden Reviewer",
            body="This draft must stay private.",
            rating=5,
            language=PublicReview.Language.ENGLISH,
            is_approved_for_publication=False,
            is_active=True,
        )

    def test_rating_validation_is_bounded_to_five_stars(self):
        review = PublicReview(
            reviewer_name="Invalid",
            body="Invalid rating",
            rating=6,
            language=PublicReview.Language.ENGLISH,
        )
        with self.assertRaises(ValidationError):
            review.full_clean()

    def test_home_renders_only_approved_active_reviews(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ar_review.body)
        self.assertContains(response, self.en_review.body)
        self.assertNotContains(response, "This draft must stay private.")
        self.assertContains(response, 'data-review-surface="populated"')
        self.assertContains(response, "public-closeout.js")

    def test_reviews_page_filters_arabic_and_english(self):
        ar_response = self.client.get(reverse("reviews"), {"filter": "ar"})
        self.assertEqual(ar_response.status_code, 200)
        self.assertContains(ar_response, self.ar_review.body)
        self.assertNotContains(ar_response, self.en_review.body)

        en_response = self.client.get(reverse("reviews_en"), {"filter": "en"})
        self.assertEqual(en_response.status_code, 200)
        self.assertContains(en_response, self.en_review.body)
        self.assertNotContains(en_response, self.ar_review.body)
        self.assertNotContains(en_response, "This draft must stay private.")

    def test_google_source_summary_is_owner_configured_not_derived_from_curated_rows(self):
        SystemSetting.objects.create(
            key=GOOGLE_REVIEW_AVERAGE_KEY,
            value="4.5",
            value_type=SystemSetting.ValueType.STRING,
        )
        SystemSetting.objects.create(
            key=GOOGLE_REVIEW_COUNT_KEY,
            value="61",
            value_type=SystemSetting.ValueType.INTEGER,
        )
        response = self.client.get(reverse("reviews"))
        self.assertContains(response, "4.5")
        self.assertContains(response, "61")

    def test_doctor_mobile_correction_has_separate_mobile_booking_placement(self):
        response = self.client.get(reverse("doctor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "doctor-contact-card-desktop")
        self.assertContains(response, "doctor-mobile-booking-section")
        self.assertContains(response, "public-closeout.css")

    def test_import_command_defaults_to_draft_and_can_explicitly_approve(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviews.json"
            path.write_text(
                json.dumps(
                    {
                        "source_summary": {"average_rating": 4.5, "review_count": 61},
                        "reviews": [
                            {
                                "reviewer_name": "Imported Reviewer",
                                "body": "Imported public review.",
                                "rating": 5,
                                "language": "en",
                                "source": "google",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            call_command("import_public_reviews", str(path))
            review = PublicReview.objects.get(reviewer_name="Imported Reviewer")
            self.assertFalse(review.is_approved_for_publication)

            call_command("import_public_reviews", str(path), approve=True)
            review.refresh_from_db()
            self.assertTrue(review.is_approved_for_publication)
            self.assertEqual(SystemSetting.objects.get(key=GOOGLE_REVIEW_COUNT_KEY).value, "61")


class PublicCaseGroupingTests(TestCase):
    def test_same_visit_media_are_grouped_and_before_after_are_recognized(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(full_name="Synthetic Patient", phone_raw="0000000000")
            visit = VisitRecord.objects.create(patient=patient)
            before = RecordMedia.objects.create(
                patient=patient,
                visit=visit,
                media_type=RecordMedia.MediaType.IMAGE,
                file=SimpleUploadedFile("before.png", b"before", content_type="image/png"),
                title="قبل",
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )
            after = RecordMedia.objects.create(
                patient=patient,
                visit=visit,
                media_type=RecordMedia.MediaType.IMAGE,
                file=SimpleUploadedFile("after.png", b"after", content_type="image/png"),
                title="بعد",
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )
            video = RecordMedia.objects.create(
                patient=patient,
                visit=visit,
                media_type=RecordMedia.MediaType.SHORT_VIDEO,
                file=SimpleUploadedFile("case.mp4", b"video", content_type="video/mp4"),
                title="حالة مصرح بعرضها",
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )

            groups = grouped_public_cases("ar")
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["before"]["public_id"], before.public_id)
            self.assertEqual(groups[0]["after"]["public_id"], after.public_id)
            self.assertEqual(groups[0]["primary"]["public_id"], video.public_id)

    def test_canonical_role_titles_are_not_public_headlines_and_note_is_resolved_once(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Hidden Grouping Patient",
                phone_raw="0000000001",
            )
            visit = VisitRecord.objects.create(patient=patient)
            note = "Synthetic consistent public case note."
            rows = (
                (RecordMedia.MediaType.IMAGE, "before.jpg", "image/jpeg", "Before"),
                (RecordMedia.MediaType.IMAGE, "after.jpg", "image/jpeg", "After"),
                (RecordMedia.MediaType.SHORT_VIDEO, "case.mp4", "video/mp4", ""),
            )
            for media_type, filename, content_type, title in rows:
                RecordMedia.objects.create(
                    patient=patient,
                    visit=visit,
                    media_type=media_type,
                    file=SimpleUploadedFile(filename, b"synthetic", content_type=content_type),
                    title=title,
                    description=note,
                    visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                    consent_confirmed=True,
                    is_active=True,
                )

            groups = grouped_public_cases("en")

            self.assertEqual(len(groups), 1)
            group = groups[0]
            self.assertEqual(len(group["items"]), 3)
            self.assertEqual(group["before"]["title"], "Before")
            self.assertEqual(group["after"]["title"], "After")
            self.assertEqual(group["primary"]["media_type"], RecordMedia.MediaType.SHORT_VIDEO)
            self.assertEqual(group["display_title"], "Authorized case 1")
            self.assertEqual(group["description"], note)

    def test_legitimate_non_role_title_remains_the_public_case_title(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Legitimate Title Patient",
                phone_raw="0000000002",
            )
            media = RecordMedia.objects.create(
                patient=patient,
                media_type=RecordMedia.MediaType.IMAGE,
                file=SimpleUploadedFile("case.jpg", b"synthetic", content_type="image/jpeg"),
                title="Synthetic public-safe case title",
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )

            group = grouped_public_cases("en")[0]

            self.assertEqual(group["primary"]["public_id"], media.public_id)
            self.assertEqual(group["display_title"], "Synthetic public-safe case title")
