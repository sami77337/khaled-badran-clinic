from datetime import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, DoctorSchedule
from apps.core.models import SystemSetting
from apps.patients.models import Patient


SETTING_DEFAULTS = [
    (SystemSetting.BOOKING_ENABLED, "true", SystemSetting.ValueType.BOOLEAN, "Enable public booking."),
    (SystemSetting.BOOKING_MIN_LEAD_MINUTES, "180", SystemSetting.ValueType.INTEGER, "Minimum lead time before a public booking."),
    (SystemSetting.BOOKING_MAX_DAYS_AHEAD, "30", SystemSetting.ValueType.INTEGER, "Maximum public booking window in days."),
    (SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES, "15", SystemSetting.ValueType.INTEGER, "Public booking slot interval."),
    (
        SystemSetting.APPOINTMENT_REMINDER_OFFSET_MINUTES,
        "180",
        SystemSetting.ValueType.DURATION_MINUTES,
        "Default appointment reminder offset.",
    ),
]

DEMO_SCHEDULES = [
    (0, time(9, 0), time(16, 0)),
    (1, time(9, 0), time(16, 0)),
    (2, time(9, 0), time(16, 0)),
    (3, time(9, 0), time(16, 0)),
    (5, time(10, 0), time(14, 0)),
]


class Command(BaseCommand):
    help = "Seed safe demo booking settings and doctor schedules without patient or appointment data."

    def handle(self, *args, **options):
        call_command("seed_public_content", stdout=self.stdout)
        doctor = Doctor.objects.filter(is_active=True).order_by("display_order", "id").first()
        if doctor is None:
            self.stdout.write(self.style.ERROR("No active doctor exists after public content seed."))
            return

        settings_created = 0
        settings_updated = 0
        for key, value, value_type, description in SETTING_DEFAULTS:
            _, created = SystemSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": value,
                    "value_type": value_type,
                    "description": description,
                },
            )
            if created:
                settings_created += 1
            else:
                settings_updated += 1

        schedules_created = 0
        schedules_updated = 0
        for weekday, start_time, end_time in DEMO_SCHEDULES:
            _, created = DoctorSchedule.objects.update_or_create(
                doctor=doctor,
                weekday=weekday,
                start_time=start_time,
                defaults={
                    "end_time": end_time,
                    "is_active": True,
                },
            )
            if created:
                schedules_created += 1
            else:
                schedules_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded booking demo setup: "
                f"settings_created={settings_created}, "
                f"settings_updated={settings_updated}, "
                f"schedules_created={schedules_created}, "
                f"schedules_updated={schedules_updated}."
            )
        )
        self.stdout.write(
            "No patients, appointments, WhatsApp messages, uploads, secrets, or payments were created."
        )
        self.stdout.write(
            f"Current patient_count={Patient.objects.count()}, appointment_count={Appointment.objects.count()}."
        )
