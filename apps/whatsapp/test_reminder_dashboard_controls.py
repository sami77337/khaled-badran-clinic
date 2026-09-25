from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.core.models import SystemSetting
from apps.patients.models import Patient
from apps.whatsapp import booking
from apps.whatsapp.test_meta import META_SETTINGS, SYNTHETIC_PHONE


@override_settings(**META_SETTINGS)
class ReminderDashboardControlsTests(TestCase):
    def setUp(self):
        self.doctor = Doctor.objects.create(
            full_name_ar="Synthetic",
            full_name_en="Synthetic",
        )
        self.patient = Patient.objects.create(
            full_name="Synthetic",
            phone_e164=SYNTHETIC_PHONE,
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="Synthetic",
            name_en="Synthetic",
            duration_minutes=30,
        )
        self.now = timezone.now()
        self.appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            visit_type=self.visit_type,
            starts_at=self.now + timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1, minutes=30),
            whatsapp_phone_e164=SYNTHETIC_PHONE,
        )

    def test_global_reminder_setting_gates_due_query_and_send(self):
        self.assertIn(
            self.appointment.pk,
            booking.due_reminders(self.now).values_list("pk", flat=True),
        )
        SystemSetting.objects.update_or_create(
            key=SystemSetting.APPOINTMENT_REMINDER_ENABLED,
            defaults={
                "value": "false",
                "value_type": SystemSetting.ValueType.BOOLEAN,
                "description": "Enable automatic appointment reminders.",
            },
        )

        self.assertFalse(booking.due_reminders(self.now).exists())
        with patch("apps.whatsapp.meta.send_appointment_notification") as sender:
            self.assertEqual(
                booking.send_due_reminder(self.appointment.pk),
                "skipped",
            )
        sender.assert_not_called()
        self.appointment.refresh_from_db()
        self.assertIsNone(self.appointment.reminder_sent_at)
