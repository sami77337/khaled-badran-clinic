from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.clinic.models import Doctor, VisitType
from apps.patients.models import Patient
from apps.whatsapp.meta import WhatsAppDeliveryError


@override_settings(
    WHATSAPP_META_ENABLED=True,
    WHATSAPP_DEFAULT_LANGUAGE="ar",
)
class WhatsAppReminderTests(TestCase):
    def setUp(self):
        self.doctor = Doctor.objects.create(full_name_ar="طبيب تجريبي", full_name_en="Synthetic Doctor")
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="زيارة تجريبية",
            name_en="Synthetic Visit",
            duration_minutes=30,
        )
        self.patient = Patient.objects.create(
            full_name="Synthetic Patient",
            phone_raw="+962790000002",
            phone_e164="+962790000002",
            whatsapp_phone_raw="+962790000002",
            whatsapp_phone_e164="+962790000002",
        )

    def appointment(self, **overrides):
        starts_at = overrides.pop("starts_at", timezone.now() + timedelta(hours=2))
        values = {
            "doctor": self.doctor,
            "patient": self.patient,
            "visit_type": self.visit_type,
            "starts_at": starts_at,
            "ends_at": starts_at + timedelta(minutes=30),
            "reminder_offset": timedelta(hours=3),
            "status": Appointment.Status.CONFIRMED,
            "reminder_enabled": True,
            "whatsapp_phone_raw": "+962790000002",
            "whatsapp_phone_e164": "+962790000002",
        }
        values.update(overrides)
        return Appointment.objects.create(**values)

    @patch("apps.whatsapp.management.commands.send_whatsapp_reminders.send_appointment_reminder", return_value=True)
    def test_due_reminder_marks_sent_after_success(self, sender):
        appointment = self.appointment()
        output = StringIO()
        call_command("send_whatsapp_reminders", stdout=output)
        appointment.refresh_from_db()
        self.assertIsNotNone(appointment.reminder_sent_at)
        sender.assert_called_once()
        self.assertNotIn(self.patient.phone_e164, output.getvalue())

    @patch("apps.whatsapp.management.commands.send_whatsapp_reminders.send_appointment_reminder", return_value=True)
    def test_ineligible_appointments_are_excluded(self, sender):
        self.appointment(status=Appointment.Status.CANCELLED)
        self.appointment(starts_at=timezone.now() + timedelta(hours=4), reminder_enabled=False)
        self.appointment(
            starts_at=timezone.now() + timedelta(hours=6),
            reminder_offset=timedelta(hours=8),
            reminder_sent_at=timezone.now(),
        )
        call_command("send_whatsapp_reminders", stdout=StringIO())
        sender.assert_not_called()

    @patch(
        "apps.whatsapp.management.commands.send_whatsapp_reminders.send_appointment_reminder",
        side_effect=WhatsAppDeliveryError("delivery unavailable"),
    )
    def test_provider_failure_leaves_reminder_retryable(self, sender):
        appointment = self.appointment()
        call_command("send_whatsapp_reminders", stdout=StringIO())
        appointment.refresh_from_db()
        self.assertIsNone(appointment.reminder_sent_at)
        sender.assert_called_once()

    @patch("apps.whatsapp.signals.send_booking_confirmation", return_value=True)
    def test_public_booking_history_triggers_confirmation_after_commit(self, sender):
        appointment = self.appointment(starts_at=timezone.now() + timedelta(days=1))
        with self.captureOnCommitCallbacks(execute=True):
            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                old_status="",
                new_status=Appointment.Status.CONFIRMED,
                note="Created through public booking.",
            )
        sender.assert_called_once()

    @patch("apps.whatsapp.signals.send_booking_confirmation", return_value=True)
    def test_other_history_does_not_trigger_confirmation(self, sender):
        appointment = self.appointment(starts_at=timezone.now() + timedelta(days=1))
        with self.captureOnCommitCallbacks(execute=True):
            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                old_status="",
                new_status=Appointment.Status.CONFIRMED,
                note="Created by staff.",
            )
        sender.assert_not_called()
