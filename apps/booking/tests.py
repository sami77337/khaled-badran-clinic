
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.patients.models import Patient


class AppointmentModelTests(TestCase):
    def setUp(self):
        self.doctor = Doctor.objects.create(
            full_name_ar="خالد حسان بدران",
            full_name_en="Khaled Hassan Badran",
            title_ar="د.",
            title_en="Dr.",
        )
        self.patient = Patient.objects.create(
            full_name="Test Patient",
            phone_raw="0790000000",
            phone_e164="+962790000000",
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="كشف جديد",
            name_en="New consultation",
            duration_minutes=30,
        )
        self.starts_at = timezone.now().replace(microsecond=0) + timedelta(days=1)

    def create_appointment(self):
        return Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            visit_type=self.visit_type,
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(minutes=30),
        )

    def test_default_status_is_confirmed(self):
        appointment = self.create_appointment()

        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

    def test_default_reminder_offset_is_three_hours(self):
        appointment = self.create_appointment()

        self.assertEqual(appointment.reminder_offset, timedelta(hours=3))
        self.assertEqual(
            appointment.reminder_due_at,
            self.starts_at - timedelta(hours=3),
        )
