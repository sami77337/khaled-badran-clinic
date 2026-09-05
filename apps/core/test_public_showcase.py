import json
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.patients.models import Patient
from apps.records.models import PublicCase, PublicCaseMedia, RecordMedia

from .models import PublicReview, SystemSetting
from .showcase import (
    GOOGLE_REVIEW_AVERAGE_KEY,
    GOOGLE_REVIEW_COUNT_KEY,
    grouped_public_cases,
)


class PublicReviewShowcaseTests(TestCase):
    def setUp(self):
        self.ar_review = PublicReview.objects.create(
            reviewer_name="Arabic Reviewer",
            body="Arabic synthetic approved review.",
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
        self.assertContains(ar_response, self.ar_review.body)
        self.assertNotContains(ar_response, self.en_review.body)

        en_response = self.client.get(reverse("reviews_en"), {"filter": "en"})
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
    @classmethod
    def setUpClass(cls):
        cls._public_media_tempdir = TemporaryDirectory()
        cls._public_media_override = override_settings(
            PUBLIC_CASE_MEDIA_ROOT=Path(cls._public_media_tempdir.name)
        )
        cls._public_media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._public_media_override.disable()
        cls._public_media_tempdir.cleanup()

    def create_case(self, **kwargs):
        defaults = {
            "title": "Standalone marketing case",
            "note": "Public-safe marketing note.",
            "detail_note": "Detailed public-safe marketing note.",
            "consent_confirmed": True,
            "is_published": True,
        }
        defaults.update(kwargs)
        return PublicCase.objects.create(**defaults)

    def create_media(
        self,
        *,
        public_case=None,
        role=PublicCaseMedia.Role.PRIMARY,
        media_type=PublicCaseMedia.MediaType.IMAGE,
        name=None,
        **kwargs,
    ):
        public_case = public_case or self.create_case()
        if name is None:
            name = "marketing.mp4" if media_type == PublicCaseMedia.MediaType.SHORT_VIDEO else "marketing.jpg"
        content_type = "video/mp4" if media_type == PublicCaseMedia.MediaType.SHORT_VIDEO else "image/jpeg"
        defaults = {
            "public_case": public_case,
            "role": role,
            "media_type": media_type,
            "file": SimpleUploadedFile(name, b"synthetic-marketing-bytes", content_type=content_type),
            "consent_confirmed": True,
            "is_active": True,
        }
        defaults.update(kwargs)
        return PublicCaseMedia.objects.create(**defaults)

    def test_grouping_uses_only_independent_marketing_media(self):
        patient = Patient.objects.create(full_name="Private Patient", phone_raw="0790000101")
        medical = RecordMedia.objects.create(
            patient=patient,
            media_type=RecordMedia.MediaType.IMAGE,
            file=SimpleUploadedFile("medical.jpg", b"medical", content_type="image/jpeg"),
            title="Private medical title",
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
        )
        case = self.create_case(title="Public marketing title")
        marketing = self.create_media(public_case=case)

        grouped = grouped_public_cases("en")

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["case_id"], case.pk)
        self.assertEqual(grouped[0]["items"][0]["public_id"], marketing.public_id)
        rendered = str(grouped)
        self.assertNotIn(patient.full_name, rendered)
        self.assertNotIn(medical.title, rendered)
        self.assertNotIn(str(medical.public_id), rendered)

    def test_public_eligibility_requires_both_consents_active_valid_role_and_existing_storage(self):
        case = self.create_case()
        eligible = self.create_media(public_case=case, role=PublicCaseMedia.Role.BEFORE)
        unconsented = self.create_media(public_case=case, role=PublicCaseMedia.Role.AFTER, consent_confirmed=False)
        inactive = self.create_media(public_case=case, role=PublicCaseMedia.Role.PRIMARY, is_active=False)
        invalid = self.create_media(public_case=case, role=PublicCaseMedia.Role.PRIMARY)
        PublicCaseMedia.objects.filter(pk=invalid.pk).update(role="")
        missing = self.create_media(public_case=case, role=PublicCaseMedia.Role.AFTER)
        missing.file.storage.delete(missing.file.name)

        grouped = grouped_public_cases("en")
        public_ids = [item["public_id"] for item in grouped[0]["items"]]

        self.assertEqual(public_ids, [eligible.public_id])
        self.assertNotIn(unconsented.public_id, public_ids)
        self.assertNotIn(inactive.public_id, public_ids)
        self.assertNotIn(invalid.public_id, public_ids)
        self.assertNotIn(missing.public_id, public_ids)

    def test_case_consent_and_publication_are_required(self):
        unpublished = self.create_case(title="Unpublished", is_published=False)
        self.create_media(public_case=unpublished)
        unconsented = self.create_case(title="Unconsented", consent_confirmed=False)
        self.create_media(public_case=unconsented)

        self.assertEqual(grouped_public_cases("en"), [])

    def test_video_cover_is_not_a_standalone_public_slide(self):
        case = self.create_case()
        self.create_media(public_case=case, role=PublicCaseMedia.Role.VIDEO_COVER)

        self.assertEqual(grouped_public_cases("en"), [])

    def test_role_labels_are_singular_or_localized_multiple_without_one_of_one(self):
        case = self.create_case(detail_note="")
        self.create_media(public_case=case, role=PublicCaseMedia.Role.BEFORE)
        single_en = grouped_public_cases("en")[0]
        single_ar = grouped_public_cases("ar")[0]
        self.assertEqual(single_en["before_items"][0]["label"], "Before image")
        self.assertEqual(single_ar["before_items"][0]["label"], "صورة قبل")
        self.assertNotIn("1 of 1", str(single_en))
        self.assertNotIn("1 من 1", str(single_ar))

        self.create_media(public_case=case, role=PublicCaseMedia.Role.BEFORE)
        multi_en = grouped_public_cases("en")[0]
        multi_ar = grouped_public_cases("ar")[0]
        self.assertEqual(multi_en["before_items"][0]["label"], "Before image 1 of 2")
        self.assertEqual(multi_ar["before_items"][0]["label"], "صورة قبل 1 من 2")

    def test_video_and_detailed_note_are_counted_as_carousel_slides(self):
        case = self.create_case(detail_note="Detail slide")
        video = self.create_media(
            public_case=case,
            role=PublicCaseMedia.Role.VIDEO,
            media_type=PublicCaseMedia.MediaType.SHORT_VIDEO,
        )

        group = grouped_public_cases("en")[0]

        self.assertEqual(group["video_items"][0]["public_id"], video.public_id)
        self.assertEqual(group["video_items"][0]["label"], "Video")
        self.assertEqual(len(group["carousel_items"]), 2)
        self.assertEqual(group["carousel_items"][-1]["kind"], "note")

    def test_ordering_and_limit_are_deterministic(self):
        older = self.create_case(title="Older")
        newer = self.create_case(title="Newer")
        self.create_media(public_case=older)
        self.create_media(public_case=newer)

        first = grouped_public_cases("en", limit=1)
        second = grouped_public_cases("en", limit=1)

        self.assertEqual(first[0]["case_id"], newer.pk)
        self.assertEqual(first, second)
