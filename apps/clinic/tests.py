
from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from apps.booking.models import Appointment
from apps.patients.models import Patient

from .models import ClinicProfile, Doctor, DoctorScheduleOverride, VisitType


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


class DoctorScheduleOverrideModelTests(TestCase):
    def setUp(self):
        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب",
            full_name_en="Doctor",
        )
        self.other_doctor = Doctor.objects.create(
            full_name_ar="طبيب آخر",
            full_name_en="Other Doctor",
        )
        self.day = date(2026, 9, 10)

    def make_override(self, *, doctor=None, day=None, start=time(9), end=time(12), active=True):
        override = DoctorScheduleOverride(
            doctor=doctor or self.doctor,
            date=day or self.day,
            start_time=start,
            end_time=end,
            is_active=active,
        )
        override.full_clean()
        override.save()
        return override

    def test_valid_single_interval(self):
        override = self.make_override()

        self.assertTrue(override.is_active)

    def test_valid_multiple_non_overlapping_intervals(self):
        self.make_override(start=time(9), end=time(12))
        second = self.make_override(start=time(16), end=time(18))

        self.assertEqual(DoctorScheduleOverride.objects.filter(is_active=True).count(), 2)
        self.assertEqual(second.start_time, time(16))

    def test_start_equal_to_end_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.make_override(start=time(9), end=time(9))

    def test_start_after_end_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.make_override(start=time(10), end=time(9))

    def test_overlapping_active_interval_is_rejected(self):
        self.make_override(start=time(9), end=time(13))

        with self.assertRaises(ValidationError):
            self.make_override(start=time(12), end=time(16))

    def test_back_to_back_intervals_are_accepted(self):
        self.make_override(start=time(9), end=time(12))

        second = self.make_override(start=time(12), end=time(16))

        self.assertEqual(second.start_time, time(12))

    def test_different_dates_do_not_conflict(self):
        self.make_override(start=time(9), end=time(13))

        second = self.make_override(
            day=date(2026, 9, 11),
            start=time(12),
            end=time(16),
        )

        self.assertEqual(second.date, date(2026, 9, 11))

    def test_inactive_interval_does_not_block(self):
        self.make_override(start=time(9), end=time(13), active=False)

        active = self.make_override(start=time(12), end=time(16))

        self.assertTrue(active.is_active)

    def test_different_doctors_do_not_conflict(self):
        self.make_override(start=time(9), end=time(13))

        other = self.make_override(
            doctor=self.other_doctor,
            start=time(12),
            end=time(16),
        )

        self.assertEqual(other.doctor, self.other_doctor)


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
