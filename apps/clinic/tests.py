
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.booking.models import Appointment
from apps.patients.models import Patient

from .models import ClinicProfile, Doctor, VisitType


class VisitTypeModelTests(TestCase):
    def test_price_is_visible_only_when_enabled_and_present(self):
        visit_type = VisitType.objects.create(
            name_ar="كشف جديد",
            name_en="New consultation",
            duration_minutes=30,
            price=Decimal("25.00"),
            show_price_to_patient=True,
        )

        self.assertTrue(visit_type.is_price_visible_to_patient)
        self.assertEqual(visit_type.patient_visible_price, Decimal("25.00"))

    def test_price_is_hidden_when_visibility_flag_is_disabled(self):
        visit_type = VisitType.objects.create(
            name_ar="مراجعة",
            name_en="Follow-up",
            duration_minutes=15,
            price=Decimal("15.00"),
            show_price_to_patient=False,
        )

        self.assertFalse(visit_type.is_price_visible_to_patient)
        self.assertIsNone(visit_type.patient_visible_price)

    def test_missing_price_is_not_visible_to_patient(self):
        visit_type = VisitType.objects.create(
            name_ar="استشارة",
            name_en="Consultation",
            duration_minutes=30,
            show_price_to_patient=True,
        )

        self.assertFalse(visit_type.is_price_visible_to_patient)
        self.assertIsNone(visit_type.patient_visible_price)


class DoctorModelTests(TestCase):
    def test_doctor_has_arabic_and_english_display_names(self):
        doctor = Doctor.objects.create(
            full_name_ar="خالد حسان بدران",
            full_name_en="Khaled Hassan Badran",
            title_ar="د.",
            title_en="Dr.",
        )

        self.assertEqual(doctor.display_name_ar, "د. خالد حسان بدران")
        self.assertEqual(doctor.display_name_en, "Dr. Khaled Hassan Badran")


class SeedPublicContentCommandTests(TestCase):
    def call_seed(self):
        output = StringIO()
        call_command("seed_public_content", stdout=output)
        return output.getvalue()

    def test_seed_command_creates_public_content(self):
        output = self.call_seed()

        self.assertIn("Seeded public content", output)
        self.assertEqual(ClinicProfile.objects.count(), 1)
        self.assertEqual(Doctor.objects.count(), 1)
        self.assertEqual(VisitType.objects.count(), 9)
        self.assertTrue(
            ClinicProfile.objects.filter(
                official_name_ar="عيادة الدكتور خالد بدران",
                official_name_en="Dr. Khaled Badran Clinic",
            ).exists()
        )
        self.assertTrue(
            VisitType.objects.filter(
                name_ar="كشف جديد",
                name_en="New consultation",
                price__isnull=True,
                show_price_to_patient=False,
            ).exists()
        )

    def test_seed_command_is_idempotent(self):
        self.call_seed()
        self.call_seed()

        self.assertEqual(ClinicProfile.objects.count(), 1)
        self.assertEqual(Doctor.objects.count(), 1)
        self.assertEqual(VisitType.objects.count(), 9)

    def test_seed_command_does_not_create_patient_or_appointment_records(self):
        self.call_seed()

        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(Appointment.objects.count(), 0)
