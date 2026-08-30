import json
import tempfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.patients.models import Patient
from apps.records.models import PublicCase, RecordMedia, RecordMediaFolder, VisitRecord
from apps.records.public_cases import encode_public_case_title

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
    def test_explicit_case_groups_media_across_different_visits_and_honors_case_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Cross Visit Case Patient",
                phone_raw="0000000099",
            )
            reference_visit = VisitRecord.objects.create(patient=patient)
            before_visit = VisitRecord.objects.create(patient=patient)
            after_visit = VisitRecord.objects.create(patient=patient)
            public_case = PublicCase.objects.create(
                patient=patient,
                reference_visit=reference_visit,
                title="Explicit cross-visit public case",
                note="One case-level note.",
                consent_confirmed=True,
                is_published=True,
            )
            before = RecordMedia.objects.create(
                patient=patient,
                visit=before_visit,
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.BEFORE,
                media_type=RecordMedia.MediaType.IMAGE,
                file=SimpleUploadedFile("cross-before.jpg", b"before", content_type="image/jpeg"),
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )
            after = RecordMedia.objects.create(
                patient=patient,
                visit=after_visit,
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.AFTER,
                media_type=RecordMedia.MediaType.IMAGE,
                file=SimpleUploadedFile("cross-after.jpg", b"after", content_type="image/jpeg"),
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )

            groups = grouped_public_cases("en")

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["display_title"], public_case.title)
            self.assertEqual(groups[0]["description"], public_case.note)
            self.assertEqual(groups[0]["before"]["public_id"], before.public_id)
            self.assertEqual(groups[0]["after"]["public_id"], after.public_id)
            self.assertEqual(
                [item["public_id"] for item in groups[0]["carousel_items"]],
                [before.public_id, after.public_id],
            )
            self.assertEqual(
                [item["label"] for item in groups[0]["carousel_items"]],
                ["Before 1 of 1", "After 1 of 1"],
            )

            public_case.is_published = False
            public_case.save(update_fields=["is_published"])
            self.assertEqual(grouped_public_cases("en"), [])

            public_case.is_published = True
            public_case.consent_confirmed = False
            public_case.save(update_fields=["is_published", "consent_confirmed"])
            self.assertEqual(grouped_public_cases("en"), [])

    def test_same_visit_media_are_grouped_and_before_after_are_recognized(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(full_name="Synthetic Patient", phone_raw="0000000000")
            visit = VisitRecord.objects.create(patient=patient)
            public_case = PublicCase.objects.create(
                patient=patient,
                reference_visit=visit,
                consent_confirmed=True,
                is_published=True,
            )
            before = RecordMedia.objects.create(
                patient=patient,
                visit=visit,
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.BEFORE,
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
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.AFTER,
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
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.VIDEO,
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
            self.assertEqual(
                {item["label"] for item in groups[0]["carousel_items"]},
                {"\u0642\u0628\u0644 1 \u0645\u0646 1", "\u0628\u0639\u062f 1 \u0645\u0646 1", "\u0641\u064a\u062f\u064a\u0648 1 \u0645\u0646 1"},
            )

    def test_canonical_role_titles_are_not_public_headlines_and_note_is_resolved_once(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Hidden Grouping Patient",
                phone_raw="0000000001",
            )
            visit = VisitRecord.objects.create(patient=patient)
            note = "Synthetic consistent public case note."
            public_case = PublicCase.objects.create(
                patient=patient,
                reference_visit=visit,
                note=note,
                consent_confirmed=True,
                is_published=True,
            )
            rows = (
                (RecordMedia.MediaType.IMAGE, "before.jpg", "image/jpeg", "Before", "before"),
                (RecordMedia.MediaType.IMAGE, "after.jpg", "image/jpeg", "After", "after"),
                (RecordMedia.MediaType.IMAGE, "primary.jpg", "image/jpeg", "Primary", "primary"),
                (RecordMedia.MediaType.SHORT_VIDEO, "case.mp4", "video/mp4", "", "video"),
            )
            for media_type, filename, content_type, title, role in rows:
                RecordMedia.objects.create(
                    patient=patient,
                    visit=visit,
                    public_case=public_case,
                    public_case_role=role,
                    media_type=media_type,
                    file=SimpleUploadedFile(filename, b"synthetic", content_type=content_type),
                    title=title,
                    description=f"INTERNAL-{role.upper()}-DESCRIPTION-MUST-STAY-HIDDEN",
                    visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                    consent_confirmed=True,
                    is_active=True,
                )

            groups = grouped_public_cases("en")

            self.assertEqual(len(groups), 1)
            group = groups[0]
            self.assertEqual(len(group["items"]), 4)
            self.assertEqual(group["before"]["role"], "before")
            self.assertEqual(group["after"]["role"], "after")
            self.assertNotIn("title", group["before"])
            self.assertNotIn("description", group["after"])
            self.assertEqual(group["primary"]["media_type"], RecordMedia.MediaType.SHORT_VIDEO)
            self.assertEqual(group["display_title"], "Authorized case 1")
            self.assertEqual(group["description"], note)
            self.assertEqual(
                [item["label"] for item in group["carousel_items"]],
                [
                    "Before 1 of 1",
                    "After 1 of 1",
                    "Case Image 1 of 1",
                    "Video 1 of 1",
                ],
            )
            self.assertNotIn("INTERNAL-", str(group["carousel_items"]))
            self.assertTrue(
                all(
                    "title" not in item and "description" not in item
                    for item in group["carousel_items"]
                )
            )
            arabic_labels = [
                item["label"] for item in grouped_public_cases("ar")[0]["carousel_items"]
            ]
            self.assertEqual(
                arabic_labels,
                [
                    "\u0642\u0628\u0644 1 \u0645\u0646 1",
                    "\u0628\u0639\u062f 1 \u0645\u0646 1",
                    "\u0635\u0648\u0631\u0629 \u0627\u0644\u062d\u0627\u0644\u0629 1 \u0645\u0646 1",
                    "\u0641\u064a\u062f\u064a\u0648 1 \u0645\u0646 1",
                ],
            )

    def test_case_metadata_never_falls_back_to_record_media_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Metadata Boundary Patient",
                phone_raw="0000000004",
            )
            public_case = PublicCase.objects.create(
                patient=patient,
                title="",
                note="",
                consent_confirmed=True,
                is_published=True,
            )
            RecordMedia.objects.create(
                patient=patient,
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.BEFORE,
                media_type=RecordMedia.MediaType.IMAGE,
                file=SimpleUploadedFile("before.jpg", b"before", content_type="image/jpeg"),
                title="INTERNAL-ROLE-TITLE-MUST-STAY-HIDDEN",
                description="INTERNAL-MEDIA-NOTE-MUST-STAY-HIDDEN",
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )

            group = grouped_public_cases("en")[0]

            self.assertEqual(group["display_title"], "Authorized case 1")
            self.assertEqual(group["description"], "")
            self.assertNotIn("INTERNAL-ROLE-TITLE-MUST-STAY-HIDDEN", str(group))
            self.assertNotIn("INTERNAL-MEDIA-NOTE-MUST-STAY-HIDDEN", str(group))

    def test_legitimate_non_role_title_remains_the_public_case_title(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Legitimate Title Patient",
                phone_raw="0000000002",
            )
            public_case = PublicCase.objects.create(
                patient=patient,
                title="Synthetic public-safe case title",
                consent_confirmed=True,
                is_published=True,
            )
            media = RecordMedia.objects.create(
                patient=patient,
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.PRIMARY,
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

    def test_encoded_multi_media_cover_title_and_folder_are_grouped_safely(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Encoded Group Patient",
                phone_raw="0000000003",
            )
            visit = VisitRecord.objects.create(patient=patient)
            folder = RecordMediaFolder.objects.create(
                patient=patient,
                name="INTERNAL-FOLDER-MUST-STAY-HIDDEN",
            )
            public_title = "Public-safe encoded case title"
            note = "One public-safe note."
            public_case = PublicCase.objects.create(
                patient=patient,
                reference_visit=visit,
                title=public_title,
                note=note,
                consent_confirmed=True,
                is_published=True,
            )
            specs = (
                (RecordMedia.MediaType.IMAGE, "before-1.jpg", "image/jpeg", "before"),
                (RecordMedia.MediaType.IMAGE, "before-2.png", "image/png", "before"),
                (RecordMedia.MediaType.IMAGE, "after-1.webp", "image/webp", "after"),
                (RecordMedia.MediaType.SHORT_VIDEO, "video-1.mp4", "video/mp4", "video"),
                (RecordMedia.MediaType.SHORT_VIDEO, "video-2.mp4", "video/mp4", "video"),
                (RecordMedia.MediaType.IMAGE, "cover.jpg", "image/jpeg", "video_cover"),
            )
            for media_type, filename, content_type, role in specs:
                RecordMedia.objects.create(
                    patient=patient,
                    visit=visit,
                    folder=folder,
                    public_case=public_case,
                    public_case_role=role,
                    media_type=media_type,
                    file=SimpleUploadedFile(filename, b"synthetic", content_type=content_type),
                    title=encode_public_case_title(role, public_title),
                    description=note,
                    visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                    consent_confirmed=True,
                    is_active=True,
                )

            first_group = grouped_public_cases("en")[0]
            second_group = grouped_public_cases("en")[0]

            self.assertEqual(first_group["display_title"], public_title)
            self.assertEqual(first_group["public_title"], public_title)
            self.assertEqual(first_group["description"], note)
            self.assertEqual(len(first_group["before_items"]), 2)
            self.assertEqual(len(first_group["after_items"]), 1)
            self.assertEqual(len(first_group["video_items"]), 2)
            self.assertIsNotNone(first_group["video_cover"])
            self.assertEqual(
                first_group["teaser"]["public_id"],
                first_group["video_cover"]["public_id"],
            )
            self.assertEqual(
                first_group["video_items"][0]["poster_url"],
                first_group["video_cover"]["url"],
            )
            self.assertEqual(first_group["video_items"][1]["poster_url"], "")
            self.assertEqual(
                first_group["carousel_items"][0]["public_id"],
                first_group["video_items"][0]["public_id"],
            )
            self.assertEqual(
                first_group["carousel_items"][0]["poster_url"],
                first_group["video_cover"]["url"],
            )
            self.assertEqual(first_group["carousel_items"][1]["poster_url"], "")
            self.assertNotIn(
                first_group["video_cover"]["public_id"],
                [item["public_id"] for item in first_group["carousel_items"]],
            )
            self.assertNotIn(
                first_group["video_cover"]["public_id"],
                [item["public_id"] for item in first_group["before_items"]],
            )
            self.assertNotIn(
                first_group["video_cover"]["public_id"],
                [item["public_id"] for item in first_group["after_items"]],
            )
            self.assertNotIn("[[public-case:", str(first_group))
            self.assertNotIn(folder.name, str(first_group))
            self.assertEqual(
                [item["public_id"] for item in first_group["items"]],
                [item["public_id"] for item in second_group["items"]],
            )

    def test_video_cover_without_a_renderable_asset_does_not_create_a_public_card(self):
        with tempfile.TemporaryDirectory() as temp_dir, override_settings(PRIVATE_MEDIA_ROOT=temp_dir):
            patient = Patient.objects.create(
                full_name="Synthetic Cover Only Patient",
                phone_raw="0000000005",
            )
            public_case = PublicCase.objects.create(
                patient=patient,
                title="Cover-only case must stay absent",
                consent_confirmed=True,
                is_published=True,
            )
            RecordMedia.objects.create(
                patient=patient,
                public_case=public_case,
                public_case_role=RecordMedia.PublicCaseRole.VIDEO_COVER,
                media_type=RecordMedia.MediaType.IMAGE,
                file=SimpleUploadedFile("cover.jpg", b"cover", content_type="image/jpeg"),
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                is_active=True,
            )

            self.assertEqual(grouped_public_cases("en"), [])
