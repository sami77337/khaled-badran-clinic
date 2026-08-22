from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.patients.models import Patient
from apps.records.models import (
    IMAGE_MAX_BYTES,
    SHORT_VIDEO_MAX_BYTES,
    ClinicalNote,
    RecordMedia,
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
