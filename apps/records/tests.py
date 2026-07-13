from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.patients.models import Patient
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord


class PatientRecordTestDataMixin:
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
        media = RecordMedia.objects.create(
            patient=self.create_patient(),
            media_type=RecordMedia.MediaType.IMAGE,
            title="Synthetic private image metadata",
        )

        self.assertEqual(media.visibility, RecordMedia.Visibility.PRIVATE_ONLY)
        self.assertFalse(media.consent_confirmed)
        self.assertFalse(media.is_visible_to_patient)
        self.assertFalse(media.is_public_case_approved)
        self.assertEqual(media.get_patient_visible_metadata(), {})
        self.assertEqual(media.get_public_case_metadata(), {})

    def test_patient_visibility_is_not_public_approval(self):
        media = RecordMedia.objects.create(
            patient=self.create_patient(),
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
        media = RecordMedia.objects.create(
            patient=patient,
            visit=visit,
            media_type=RecordMedia.MediaType.IMAGE,
            title="Synthetic private media title",
            description="Synthetic private media description.",
        )

        self.assertEqual(visit.get_patient_visible_content(), {})
        self.assertEqual(note.get_patient_visible_content(), {})
        self.assertEqual(media.get_patient_visible_metadata(), {})
        self.assertEqual(media.get_public_case_metadata(), {})

    def test_no_automated_medical_generation_fields_or_file_uploads_exist(self):
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

        for model_class in (VisitRecord, ClinicalNote, RecordMedia):
            for field in model_class._meta.fields:
                with self.subTest(model=model_class.__name__, field=field.name):
                    self.assertNotIsInstance(field, models.FileField)

        self.assertIn("Manual", VisitRecord._meta.get_field("diagnosis_plan").help_text)
        self.assertIn("Manual", VisitRecord._meta.get_field("instructions").help_text)
