from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog
from apps.patients.models import Patient
from apps.records.models import (
    IMAGE_MAX_BYTES,
    SHORT_VIDEO_MAX_BYTES,
    ClinicalNote,
    PublicCase,
    RecordMedia,
    RecordMediaFolder,
    VisitRecord,
)
from apps.records.storage import private_record_media_storage


class PatientRecordTestDataMixin:
    @classmethod
    def setUpClass(cls):
        cls._private_media_tempdir = TemporaryDirectory()
        cls._private_media_override = override_settings(
            PRIVATE_MEDIA_ROOT=Path(cls._private_media_tempdir.name)
        )
        cls._private_media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._private_media_override.disable()
        cls._private_media_tempdir.cleanup()

    def create_patient(self):
        return Patient.objects.create(
            full_name="Synthetic Patient",
            phone_raw="+962700000000",
            phone_e164="+962700000000",
            date_of_birth=date(1990, 1, 1),
            gender=Patient.Gender.PREFER_NOT_TO_SAY,
        )

    def create_doctor(self):
        return Doctor.objects.create(
            full_name_ar="Synthetic Doctor",
            full_name_en="Synthetic Doctor",
            title_en="Dr.",
            specialty_en="Clinic care",
            is_active=True,
        )

    def create_visit_type(self, doctor):
        return VisitType.objects.create(
            doctor=doctor,
            name_ar="Synthetic visit",
            name_en="Synthetic visit",
            duration_minutes=30,
            is_active=True,
        )

    def create_appointment(self, patient):
        doctor = self.create_doctor()
        visit_type = self.create_visit_type(doctor)
        starts_at = timezone.now() + timedelta(days=1)
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
        )

    def create_user(self, username="records-user", is_staff=False):
        return get_user_model().objects.create_user(
            username=username,
            password="synthetic-test-password",
            is_staff=is_staff,
        )

    def synthetic_image_file(
        self,
        name="synthetic-image.jpg",
        content_type="image/jpeg",
        size=128,
    ):
        return SimpleUploadedFile(name, b"i" * size, content_type=content_type)

    def synthetic_video_file(
        self,
        name="synthetic-video.mp4",
        content_type="video/mp4",
        size=256,
    ):
        return SimpleUploadedFile(name, b"v" * size, content_type=content_type)

    def create_record_media(self, media_type=RecordMedia.MediaType.IMAGE, file=None, **kwargs):
        patient = kwargs.pop("patient", None) or self.create_patient()
        if file is None:
            file = (
                self.synthetic_video_file()
                if media_type == RecordMedia.MediaType.SHORT_VIDEO
                else self.synthetic_image_file()
            )
        if (
            kwargs.get("visibility") == RecordMedia.Visibility.APPROVED_PUBLIC_CASE
            and "public_case" not in kwargs
        ):
            kwargs["public_case"] = PublicCase.objects.create(
                patient=patient,
                consent_confirmed=True,
                is_published=True,
            )
            kwargs.setdefault(
                "public_case_role",
                (
                    RecordMedia.PublicCaseRole.VIDEO
                    if media_type == RecordMedia.MediaType.SHORT_VIDEO
                    else RecordMedia.PublicCaseRole.PRIMARY
                ),
            )
        return RecordMedia.objects.create(
            patient=patient,
            media_type=media_type,
            file=file,
            **kwargs,
        )


class PatientRecordFoundationTests(PatientRecordTestDataMixin, TestCase):
    def test_patient_record_can_be_created_with_synthetic_data(self):
        patient = self.create_patient()
        appointment = self.create_appointment(patient)

        visit = VisitRecord.objects.create(
            patient=patient,
            appointment=appointment,
            visit_reason="Synthetic visit reason.",
            doctor_notes="Synthetic doctor note.",
            diagnosis_plan="Synthetic manually written plan.",
            instructions="Synthetic manually written instructions.",
            follow_up_notes="Synthetic manually written follow-up notes.",
        )

        self.assertEqual(visit.patient, patient)
        self.assertEqual(visit.appointment, appointment)
        self.assertEqual(patient.phone, "+962700000000")
        self.assertEqual(patient.age, timezone.localdate().year - 1990)
        self.assertEqual(patient.gender, Patient.Gender.PREFER_NOT_TO_SAY)

    def test_visit_defaults_to_not_visible_to_patient(self):
        visit = VisitRecord.objects.create(
            patient=self.create_patient(),
            visit_reason="Synthetic private visit reason.",
            doctor_notes="Synthetic private doctor note.",
        )

        self.assertFalse(visit.is_visible_to_patient)
        self.assertEqual(visit.get_patient_visible_content(), {})

    def test_clinical_note_defaults_to_not_visible_to_patient(self):
        note = ClinicalNote.objects.create(
            patient=self.create_patient(),
            body="Synthetic private staff note.",
        )

        self.assertFalse(note.is_visible_to_patient)
        self.assertEqual(note.get_patient_visible_content(), {})

    def test_media_defaults_to_private_only_and_no_consent(self):
        media = self.create_record_media(
            title="Synthetic private image metadata",
        )

        self.assertEqual(media.visibility, RecordMedia.Visibility.PRIVATE_ONLY)
        self.assertFalse(media.consent_confirmed)
        self.assertFalse(media.is_visible_to_patient)
        self.assertFalse(media.is_public_case_approved)
        self.assertEqual(media.get_patient_visible_metadata(), {})
        self.assertEqual(media.get_public_case_metadata(), {})

    def test_patient_visibility_is_not_public_approval(self):
        media = self.create_record_media(
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Synthetic patient-visible short video metadata",
        )

        self.assertTrue(media.is_visible_to_patient)
        self.assertFalse(media.is_public_case_approved)
        self.assertEqual(media.get_public_case_metadata(), {})
        self.assertEqual(
            media.get_patient_visible_metadata()["title"],
            "Synthetic patient-visible short video metadata",
        )

    def test_approved_public_case_requires_confirmed_consent(self):
        media = RecordMedia(
            patient=self.create_patient(),
            media_type=RecordMedia.MediaType.IMAGE,
            file=self.synthetic_image_file(),
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=False,
        )

        with self.assertRaises(ValidationError):
            media.full_clean()

        media.consent_confirmed = True
        with self.assertRaisesMessage(
            ValidationError,
            "Approved public case media requires a public case.",
        ):
            media.full_clean()

        media.public_case = PublicCase.objects.create(
            patient=media.patient,
            consent_confirmed=True,
            is_published=True,
        )
        media.public_case_role = RecordMedia.PublicCaseRole.PRIMARY
        media.full_clean()
        media.save()

        self.assertTrue(media.is_public_case_approved)
        self.assertFalse(media.is_visible_to_patient)

    def test_no_public_medical_content_is_exposed_by_default(self):
        patient = self.create_patient()
        visit = VisitRecord.objects.create(
            patient=patient,
            visit_reason="Synthetic private reason.",
            doctor_notes="Synthetic private doctor notes.",
            diagnosis_plan="Synthetic private manual plan.",
            instructions="Synthetic private instructions.",
            follow_up_notes="Synthetic private follow-up.",
        )
        note = ClinicalNote.objects.create(
            patient=patient,
            visit=visit,
            title="Synthetic private note title",
            body="Synthetic private note body.",
        )
        media = self.create_record_media(
            patient=patient,
            visit=visit,
            title="Synthetic private media title",
            description="Synthetic private media description.",
        )

        self.assertEqual(visit.get_patient_visible_content(), {})
        self.assertEqual(note.get_patient_visible_content(), {})
        self.assertEqual(media.get_patient_visible_metadata(), {})
        self.assertEqual(media.get_public_case_metadata(), {})

    def test_no_automated_medical_generation_fields_exist(self):
        field_names = {
            field.name
            for model_class in (VisitRecord, ClinicalNote, RecordMedia)
            for field in model_class._meta.get_fields()
        }
        blocked_terms = {
            "ai",
            "automated",
            "generated",
            "recommendation",
            "triage",
            "treatment",
        }

        for field_name in field_names:
            with self.subTest(field_name=field_name):
                self.assertFalse(any(term in field_name for term in blocked_terms))

        for model_class in (VisitRecord, ClinicalNote):
            for field in model_class._meta.fields:
                with self.subTest(model=model_class.__name__, field=field.name):
                    self.assertNotIsInstance(field, models.FileField)

        self.assertIsInstance(RecordMedia._meta.get_field("file"), models.FileField)
        self.assertIn("Manual", VisitRecord._meta.get_field("diagnosis_plan").help_text)
        self.assertIn("Manual", VisitRecord._meta.get_field("instructions").help_text)


class PublicCaseModelTests(PatientRecordTestDataMixin, TestCase):
    def test_same_patient_reference_visit_is_valid(self):
        patient = self.create_patient()
        visit = VisitRecord.objects.create(patient=patient)
        public_case = PublicCase(
            patient=patient,
            reference_visit=visit,
            title="Synthetic public case",
        )

        public_case.full_clean()
        public_case.save()

        self.assertEqual(public_case.patient, patient)
        self.assertEqual(public_case.reference_visit, visit)

    def test_cross_patient_reference_visit_is_rejected(self):
        patient = self.create_patient()
        other_patient = Patient.objects.create(
            full_name="Synthetic Other Patient",
            phone_raw="+962700000001",
        )
        other_visit = VisitRecord.objects.create(patient=other_patient)
        public_case = PublicCase(patient=patient, reference_visit=other_visit)

        with self.assertRaisesMessage(
            ValidationError,
            "Reference visit must belong to the selected patient.",
        ):
            public_case.full_clean()

    def test_media_accepts_same_patient_public_case_and_explicit_image_roles(self):
        patient = self.create_patient()
        public_case = PublicCase.objects.create(patient=patient)

        for role in (
            RecordMedia.PublicCaseRole.PRIMARY,
            RecordMedia.PublicCaseRole.BEFORE,
            RecordMedia.PublicCaseRole.AFTER,
            RecordMedia.PublicCaseRole.VIDEO_COVER,
        ):
            with self.subTest(role=role):
                media = RecordMedia(
                    patient=patient,
                    public_case=public_case,
                    public_case_role=role,
                    media_type=RecordMedia.MediaType.IMAGE,
                    file=self.synthetic_image_file(name=f"{role}.jpg"),
                )
                media.full_clean()

    def test_media_accepts_video_role_for_short_video(self):
        patient = self.create_patient()
        public_case = PublicCase.objects.create(patient=patient)
        media = RecordMedia(
            patient=patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.VIDEO,
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            file=self.synthetic_video_file(),
        )

        media.full_clean()

    def test_cross_patient_public_case_is_rejected(self):
        patient = self.create_patient()
        other_patient = Patient.objects.create(
            full_name="Synthetic Public Case Owner",
            phone_raw="+962700000002",
        )
        public_case = PublicCase.objects.create(patient=other_patient)
        media = RecordMedia(
            patient=patient,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
            media_type=RecordMedia.MediaType.IMAGE,
            file=self.synthetic_image_file(),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Public case must belong to the selected patient.",
        ):
            media.full_clean()

    def test_role_requires_public_case_and_matching_media_type(self):
        patient = self.create_patient()
        public_case = PublicCase.objects.create(patient=patient)
        invalid_rows = (
            (RecordMedia.PublicCaseRole.BEFORE, RecordMedia.MediaType.SHORT_VIDEO),
            (RecordMedia.PublicCaseRole.AFTER, RecordMedia.MediaType.SHORT_VIDEO),
            (RecordMedia.PublicCaseRole.VIDEO_COVER, RecordMedia.MediaType.SHORT_VIDEO),
            (RecordMedia.PublicCaseRole.VIDEO, RecordMedia.MediaType.IMAGE),
        )

        without_case = RecordMedia(
            patient=patient,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
            media_type=RecordMedia.MediaType.IMAGE,
            file=self.synthetic_image_file(name="without-case.jpg"),
        )
        with self.assertRaisesMessage(
            ValidationError,
            "A public case role requires a public case.",
        ):
            without_case.full_clean()

        for index, (role, media_type) in enumerate(invalid_rows):
            with self.subTest(role=role, media_type=media_type):
                file = (
                    self.synthetic_video_file(name=f"invalid-{index}.mp4")
                    if media_type == RecordMedia.MediaType.SHORT_VIDEO
                    else self.synthetic_image_file(name=f"invalid-{index}.jpg")
                )
                media = RecordMedia(
                    patient=patient,
                    public_case=public_case,
                    public_case_role=role,
                    media_type=media_type,
                    file=file,
                )
                with self.assertRaises(ValidationError):
                    media.full_clean()

    def test_folder_is_independent_from_public_case(self):
        patient = self.create_patient()
        folder = RecordMediaFolder.objects.create(patient=patient, name="Internal only")
        public_case = PublicCase.objects.create(patient=patient)
        media = self.create_record_media(
            patient=patient,
            folder=folder,
            public_case=public_case,
            public_case_role=RecordMedia.PublicCaseRole.BEFORE,
        )

        self.assertEqual(media.folder, folder)
        self.assertEqual(media.public_case, public_case)

    def test_database_rejects_approved_public_media_without_public_case(self):
        media = self.create_record_media()

        with self.assertRaises(IntegrityError), transaction.atomic():
            RecordMedia.objects.filter(pk=media.pk).update(
                visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                consent_confirmed=True,
                public_case=None,
            )


class PublicCaseBackfillMigrationTests(TransactionTestCase):
    migrate_from = ("records", "0003_recordmediafolder_recordmedia_folder")
    migrate_to = ("records", "0004_recordmedia_public_case_role_publiccase_and_more")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        PatientModel = old_apps.get_model("patients", "Patient")
        VisitModel = old_apps.get_model("records", "VisitRecord")
        MediaModel = old_apps.get_model("records", "RecordMedia")

        patient = PatientModel.objects.create(
            full_name="Synthetic Migration Patient",
            phone_raw="+962700000010",
        )
        first_visit = VisitModel.objects.create(patient_id=patient.pk)
        second_visit = VisitModel.objects.create(patient_id=patient.pk)
        self.original_files = []

        def add_media(*, visit, media_type, title, description=""):
            file_name = f"records/migration-{len(self.original_files)}.dat"
            row = MediaModel.objects.create(
                patient_id=patient.pk,
                visit_id=visit.pk if visit else None,
                media_type=media_type,
                file=file_name,
                original_filename=file_name.rsplit("/", 1)[-1],
                file_size=10,
                content_type=("video/mp4" if media_type == "short_video" else "image/jpeg"),
                title=title,
                description=description,
                visibility="approved_public_case",
                consent_confirmed=True,
                is_active=True,
            )
            self.original_files.append((row.pk, file_name))
            return row

        self.first_before = add_media(
            visit=first_visit,
            media_type="image",
            title="[[public-case:before]]Clean migrated title",
            description="Migrated public note.",
        )
        self.first_after = add_media(
            visit=first_visit,
            media_type="image",
            title="After",
        )
        self.second_video = add_media(
            visit=second_visit,
            media_type="short_video",
            title="[[public-case:video]]Second migrated title",
        )
        self.second_cover = add_media(
            visit=second_visit,
            media_type="image",
            title="[[public-case:video_cover]]Second migrated title",
        )
        self.unvisited_neutral = add_media(
            visit=None,
            media_type="image",
            title="قبل",
        )
        self.unvisited_titled = add_media(
            visit=None,
            media_type="image",
            title="Independent migrated title",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes("records"))
        super().tearDown()

    def test_backfill_preserves_safe_legacy_grouping_and_media(self):
        PublicCaseModel = self.apps.get_model("records", "PublicCase")
        MediaModel = self.apps.get_model("records", "RecordMedia")
        cases = list(PublicCaseModel.objects.order_by("pk"))
        rows = {row.pk: row for row in MediaModel.objects.order_by("pk")}

        self.assertEqual(len(cases), 4)
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            rows[self.first_before.pk].public_case_id,
            rows[self.first_after.pk].public_case_id,
        )
        self.assertNotEqual(
            rows[self.first_before.pk].public_case_id,
            rows[self.second_video.pk].public_case_id,
        )
        self.assertNotEqual(
            rows[self.unvisited_neutral.pk].public_case_id,
            rows[self.unvisited_titled.pk].public_case_id,
        )
        self.assertEqual(rows[self.first_before.pk].public_case_role, "before")
        self.assertEqual(rows[self.first_after.pk].public_case_role, "after")
        self.assertEqual(rows[self.second_video.pk].public_case_role, "video")
        self.assertEqual(rows[self.second_cover.pk].public_case_role, "video_cover")
        self.assertEqual(rows[self.first_before.pk].public_case.title, "Clean migrated title")
        self.assertEqual(rows[self.first_before.pk].public_case.note, "Migrated public note.")
        self.assertEqual(rows[self.unvisited_neutral.pk].public_case.title, "")
        self.assertEqual(
            rows[self.unvisited_titled.pk].public_case.title,
            "Independent migrated title",
        )
        self.assertTrue(all(case.consent_confirmed and case.is_published for case in cases))
        self.assertEqual(
            [(pk, rows[pk].file.name) for pk, _ in self.original_files],
            self.original_files,
        )


class PublicCaseDetailNoteMigrationTests(TransactionTestCase):
    migrate_from = ("records", "0006_recordmedia_trashed_at_recordmedia_trashed_by")
    migrate_to = ("records", "0007_publiccase_detail_note")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        PatientModel = old_apps.get_model("patients", "Patient")
        PublicCaseModel = old_apps.get_model("records", "PublicCase")
        MediaModel = old_apps.get_model("records", "RecordMedia")

        patient = PatientModel.objects.create(
            full_name="Synthetic Detail Note Migration Patient",
            phone_raw="+962700000011",
        )
        self.short_original = "  Short historical public note.  "
        self.long_original = "  " + ("Long historical public note. " * 12) + "\n"
        self.short_case = PublicCaseModel.objects.create(
            patient_id=patient.pk,
            title="Short historical case",
            note=self.short_original,
            consent_confirmed=True,
            is_published=True,
        )
        self.long_case = PublicCaseModel.objects.create(
            patient_id=patient.pk,
            title="Long historical case",
            note=self.long_original,
            consent_confirmed=True,
            is_published=True,
        )
        self.media = MediaModel.objects.create(
            patient_id=patient.pk,
            public_case_id=self.long_case.pk,
            public_case_role="before",
            media_type="image",
            file="records/synthetic-detail-note-migration.jpg",
            original_filename="synthetic-detail-note-migration.jpg",
            file_size=10,
            content_type="image/jpeg",
            visibility="approved_public_case",
            consent_confirmed=True,
            is_active=True,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes("records"))
        super().tearDown()

    def test_length_classification_preserves_complete_text_and_relationships(self):
        PublicCaseModel = self.apps.get_model("records", "PublicCase")
        MediaModel = self.apps.get_model("records", "RecordMedia")
        short_case = PublicCaseModel.objects.get(pk=self.short_case.pk)
        long_case = PublicCaseModel.objects.get(pk=self.long_case.pk)
        media = MediaModel.objects.get(pk=self.media.pk)

        self.assertEqual(short_case.note, self.short_original)
        self.assertEqual(short_case.detail_note, "")
        self.assertEqual(long_case.note, "")
        self.assertEqual(long_case.detail_note, self.long_original)
        self.assertGreater(len(long_case.detail_note.strip()), 180)
        self.assertNotEqual(long_case.note, long_case.detail_note)
        self.assertEqual(media.public_case_id, long_case.pk)
        self.assertEqual(PublicCaseModel.objects.count(), 2)
        self.assertEqual(MediaModel.objects.count(), 1)



class RecordMediaFileSecurityTests(PatientRecordTestDataMixin, TestCase):
    def test_uploaded_image_is_accepted_with_allowed_type_and_size(self):
        media = self.create_record_media(file=self.synthetic_image_file(size=1024))

        self.assertEqual(media.original_filename, "synthetic-image.jpg")
        self.assertEqual(media.file_size, 1024)
        self.assertEqual(media.content_type, "image/jpeg")
        self.assertTrue(media.file.name.startswith(f"records/image/{media.public_id}/"))
        self.assertNotIn("synthetic-image", media.file.name)

    def test_uploaded_short_mp4_video_is_accepted_with_allowed_type_and_size(self):
        media = self.create_record_media(
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            file=self.synthetic_video_file(size=2048),
        )

        self.assertEqual(media.original_filename, "synthetic-video.mp4")
        self.assertEqual(media.file_size, 2048)
        self.assertEqual(media.content_type, "video/mp4")
        self.assertTrue(media.file.name.startswith(f"records/short_video/{media.public_id}/"))
        self.assertNotIn("synthetic-video", media.file.name)

    def test_invalid_image_extension_or_content_type_is_rejected(self):
        cases = [
            (
                "unsupported extension",
                self.synthetic_image_file(name="synthetic-image.gif", content_type="image/jpeg"),
                "file",
            ),
            (
                "unsupported content type",
                self.synthetic_image_file(name="synthetic-image.jpg", content_type="application/pdf"),
                "content_type",
            ),
        ]

        for label, uploaded_file, field_name in cases:
            with self.subTest(label=label):
                media = RecordMedia(
                    patient=self.create_patient(),
                    media_type=RecordMedia.MediaType.IMAGE,
                    file=uploaded_file,
                )

                with self.assertRaises(ValidationError) as context:
                    media.full_clean()

                self.assertIn(field_name, context.exception.message_dict)

    def test_invalid_video_extension_or_content_type_is_rejected(self):
        cases = [
            (
                "unsupported extension",
                self.synthetic_video_file(name="synthetic-video.mov", content_type="video/mp4"),
                "file",
            ),
            (
                "unsupported content type",
                self.synthetic_video_file(name="synthetic-video.mp4", content_type="video/quicktime"),
                "content_type",
            ),
        ]

        for label, uploaded_file, field_name in cases:
            with self.subTest(label=label):
                media = RecordMedia(
                    patient=self.create_patient(),
                    media_type=RecordMedia.MediaType.SHORT_VIDEO,
                    file=uploaded_file,
                )

                with self.assertRaises(ValidationError) as context:
                    media.full_clean()

                self.assertIn(field_name, context.exception.message_dict)

    def test_oversized_image_is_rejected(self):
        media = RecordMedia(
            patient=self.create_patient(),
            media_type=RecordMedia.MediaType.IMAGE,
            file=self.synthetic_image_file(size=IMAGE_MAX_BYTES + 1),
        )

        with self.assertRaises(ValidationError) as context:
            media.full_clean()

        self.assertIn("file_size", context.exception.message_dict)

    def test_oversized_video_is_rejected(self):
        media = RecordMedia(
            patient=self.create_patient(),
            media_type=RecordMedia.MediaType.SHORT_VIDEO,
            file=self.synthetic_video_file(size=SHORT_VIDEO_MAX_BYTES + 1),
        )

        with self.assertRaises(ValidationError) as context:
            media.full_clean()

        self.assertIn("file_size", context.exception.message_dict)

    def test_private_storage_url_is_unavailable_for_media_files(self):
        media = self.create_record_media()

        with self.assertRaises(ValueError):
            private_record_media_storage.url(media.file.name)
        with self.assertRaises(ValueError):
            media.file.url

    def test_database_file_value_is_not_public_url_or_absolute_path(self):
        media = self.create_record_media()

        stored_file = RecordMedia.objects.values_list("file", flat=True).get(pk=media.pk)

        self.assertFalse(Path(stored_file).is_absolute())
        self.assertNotIn(str(settings.PRIVATE_MEDIA_ROOT), stored_file)
        self.assertNotIn(settings.MEDIA_URL, stored_file)
        self.assertNotIn("synthetic-image", stored_file)
        self.assertTrue(stored_file.startswith(f"records/image/{media.public_id}/"))

    def test_anonymous_user_cannot_download_private_media(self):
        media = self.create_record_media()

        response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", response["Location"])

    def test_normal_non_staff_user_cannot_download_private_media(self):
        media = self.create_record_media()
        self.client.force_login(self.create_user(username="records-normal-user"))

        response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_download_active_private_media_by_public_id(self):
        media = self.create_record_media(file=self.synthetic_image_file(size=32))
        self.client.force_login(self.create_user(username="records-staff-user", is_staff=True))

        response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertNotIn(str(settings.PRIVATE_MEDIA_ROOT), response.get("Content-Disposition", ""))
        self.assertEqual(b"".join(response.streaming_content), b"i" * 32)

    def test_inactive_media_cannot_be_downloaded(self):
        media = self.create_record_media(is_active=False)
        self.client.force_login(self.create_user(username="records-inactive-staff", is_staff=True))

        response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(response.status_code, 404)

    def test_visible_to_patient_does_not_make_download_public(self):
        media = self.create_record_media(visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT)

        anonymous_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )
        self.client.force_login(self.create_user(username="records-visible-normal"))
        non_staff_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(anonymous_response.status_code, 302)
        self.assertEqual(non_staff_response.status_code, 403)
        self.assertFalse(media.is_public_case_approved)

    def test_approved_public_case_with_consent_does_not_make_download_public(self):
        media = self.create_record_media(
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
        )

        anonymous_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )
        self.client.force_login(self.create_user(username="records-public-case-normal"))
        non_staff_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(anonymous_response.status_code, 302)
        self.assertEqual(non_staff_response.status_code, 403)
        self.assertTrue(media.is_public_case_approved)
        with self.assertRaises(ValueError):
            media.file.url


class RecordMediaFolderModelTests(PatientRecordTestDataMixin, TestCase):
    def test_folder_belongs_to_patient_and_media_can_remain_unfiled(self):
        patient = self.create_patient()
        folder = RecordMediaFolder.objects.create(patient=patient, name="  Follow Up  ")
        media = self.create_record_media(patient=patient)

        self.assertEqual(folder.patient, patient)
        self.assertEqual(folder.name, "Follow Up")
        self.assertIsNone(media.folder)

    def test_same_patient_folder_assignment_works(self):
        patient = self.create_patient()
        folder = RecordMediaFolder.objects.create(patient=patient, name="Procedure")
        media = self.create_record_media(patient=patient, folder=folder)

        self.assertEqual(media.folder, folder)

    def test_cross_patient_folder_assignment_is_rejected(self):
        patient = self.create_patient()
        other_patient = Patient.objects.create(
            full_name="Synthetic Other Patient",
            phone_raw="+962700000001",
        )
        other_folder = RecordMediaFolder.objects.create(
            patient=other_patient,
            name="Other Patient Folder",
        )
        media = RecordMedia(
            patient=patient,
            folder=other_folder,
            media_type=RecordMedia.MediaType.IMAGE,
            file=self.synthetic_image_file(),
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Folder must belong to the selected patient.",
        ):
            media.full_clean()

    def test_deleting_folder_sets_media_unfiled_without_deleting_media(self):
        patient = self.create_patient()
        folder = RecordMediaFolder.objects.create(patient=patient, name="Temporary Folder")
        media = self.create_record_media(patient=patient, folder=folder)
        media_pk = media.pk

        folder.delete()
        media.refresh_from_db()

        self.assertIsNone(media.folder_id)
        self.assertTrue(RecordMedia.objects.filter(pk=media_pk).exists())

    def test_moving_folder_is_metadata_only_and_preserves_visibility_and_storage_name(self):
        patient = self.create_patient()
        first_folder = RecordMediaFolder.objects.create(patient=patient, name="First")
        second_folder = RecordMediaFolder.objects.create(patient=patient, name="Second")
        media = self.create_record_media(
            patient=patient,
            folder=first_folder,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
        )
        storage_name = media.file.name

        media.folder = second_folder
        media.save(update_fields=["folder"])
        media.refresh_from_db()

        self.assertEqual(media.folder, second_folder)
        self.assertEqual(media.file.name, storage_name)
        self.assertEqual(media.visibility, RecordMedia.Visibility.VISIBLE_TO_PATIENT)

        media.folder = None
        media.save(update_fields=["folder"])
        media.refresh_from_db()
        self.assertIsNone(media.folder_id)
        self.assertEqual(media.file.name, storage_name)
        self.assertEqual(media.visibility, RecordMedia.Visibility.VISIBLE_TO_PATIENT)

    def test_folder_rejects_blank_and_case_insensitive_same_patient_duplicates(self):
        patient = self.create_patient()
        RecordMediaFolder.objects.create(patient=patient, name="Procedure Photos")

        with self.assertRaises(ValidationError):
            RecordMediaFolder.objects.create(patient=patient, name="   ")
        with self.assertRaisesMessage(
            ValidationError,
            "A folder with this name already exists for this patient.",
        ):
            RecordMediaFolder.objects.create(patient=patient, name="procedure photos")


class PurgeTrashedRecordMediaCommandTests(PatientRecordTestDataMixin, TestCase):
    def create_trashed_media(self, *, age, patient=None):
        patient = patient or self.create_patient()
        uploader = self.create_user(username=f"purge-uploader-{RecordMedia.objects.count()}")
        media = self.create_record_media(
            patient=patient,
            uploaded_by=uploader,
            trashed_by=uploader,
            trashed_at=timezone.now() - age,
            is_active=False,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
        )
        AuditLog.objects.create(
            user=uploader,
            action=AuditLog.Action.DELETE,
            app_label="records",
            model_name="RecordMedia",
            object_id=str(media.pk),
            object_repr=f"RecordMedia {media.pk}",
            message="record_media_moved_to_trash",
            metadata={
                "action": "record_media_moved_to_trash",
                "patient_id": patient.pk,
                "media_public_id": str(media.public_id),
                "media_type": media.media_type,
            },
        )
        return media

    def test_29_day_media_is_not_purged_and_restored_media_is_not_eligible(self):
        retained = self.create_trashed_media(age=timedelta(days=29))
        restored = self.create_trashed_media(age=timedelta(days=31))
        RecordMedia.objects.filter(pk=restored.pk).update(
            trashed_at=None,
            trashed_by=None,
            is_active=True,
        )

        stdout = StringIO()
        call_command("purge_trashed_record_media", stdout=stdout)

        self.assertTrue(RecordMedia.objects.filter(pk=retained.pk).exists())
        self.assertTrue(RecordMedia.objects.filter(pk=restored.pk).exists())
        self.assertTrue(retained.file.storage.exists(retained.file.name))
        self.assertTrue(restored.file.storage.exists(restored.file.name))
        self.assertIn("Purged 0", stdout.getvalue())

    def test_exactly_or_over_30_days_is_purged_with_file_and_audit_history(self):
        exactly_eligible = self.create_trashed_media(age=timedelta(days=30))
        over_eligible = self.create_trashed_media(age=timedelta(days=31))
        public_ids = [str(exactly_eligible.public_id), str(over_eligible.public_id)]
        storage_names = [exactly_eligible.file.name, over_eligible.file.name]

        stdout = StringIO()
        call_command("purge_trashed_record_media", stdout=stdout)

        self.assertFalse(
            RecordMedia.objects.filter(
                pk__in=[exactly_eligible.pk, over_eligible.pk]
            ).exists()
        )
        for storage_name in storage_names:
            self.assertFalse(private_record_media_storage.exists(storage_name))
        for public_id in public_ids:
            self.assertTrue(
                AuditLog.objects.filter(
                    metadata__action="record_media_moved_to_trash",
                    metadata__media_public_id=public_id,
                ).exists()
            )
            purge_audit = AuditLog.objects.get(
                metadata__action="record_media_purged_after_retention",
                metadata__media_public_id=public_id,
            )
            self.assertIsNone(purge_audit.user)
            self.assertNotIn("file", str(purge_audit.metadata).lower())
        self.assertIn("Purged 2", stdout.getvalue())

    def test_storage_delete_failure_preserves_database_row_and_continues_safely(self):
        media = self.create_trashed_media(age=timedelta(days=31))
        stderr = StringIO()

        with patch.object(
            private_record_media_storage,
            "delete",
            side_effect=OSError("synthetic storage failure"),
        ):
            call_command("purge_trashed_record_media", stderr=stderr)

        self.assertTrue(RecordMedia.objects.filter(pk=media.pk).exists())
        self.assertTrue(private_record_media_storage.exists(media.file.name))
        self.assertFalse(
            AuditLog.objects.filter(
                metadata__action="record_media_purged_after_retention",
                metadata__media_public_id=str(media.public_id),
            ).exists()
        )
        self.assertIn("storage deletion failed", stderr.getvalue())
        self.assertNotIn(media.file.name, stderr.getvalue())

    def test_dry_run_is_idempotent_and_does_not_delete(self):
        media = self.create_trashed_media(age=timedelta(days=31))
        stdout = StringIO()

        call_command("purge_trashed_record_media", "--dry-run", stdout=stdout)
        call_command("purge_trashed_record_media", "--dry-run", stdout=stdout)

        self.assertTrue(RecordMedia.objects.filter(pk=media.pk).exists())
        self.assertTrue(private_record_media_storage.exists(media.file.name))
        self.assertIn("1 RecordMedia row(s) are eligible", stdout.getvalue())
