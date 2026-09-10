from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import DateTimeField, ExpressionWrapper, F
from django.utils import timezone

from apps.booking.models import Appointment
from apps.whatsapp.booking_notifications import send_appointment_reminder
from apps.whatsapp.meta import (
    WhatsAppConfigurationError,
    WhatsAppDeliveryError,
    provider_enabled,
)


ACTIVE_REMINDER_STATUSES = (
    Appointment.Status.CONFIRMED,
    Appointment.Status.RESCHEDULED,
)


class Command(BaseCommand):
    help = "Send due WhatsApp appointment reminders without exposing patient data in output."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1 or limit > 1000:
            raise CommandError("--limit must be between 1 and 1000.")
        if not provider_enabled():
            raise CommandError("WhatsApp Meta provider is not enabled.")

        now = timezone.now()
        due_expression = ExpressionWrapper(
            F("starts_at") - F("reminder_offset"),
            output_field=DateTimeField(),
        )
        candidate_ids = list(
            Appointment.objects.filter(
                status__in=ACTIVE_REMINDER_STATUSES,
                reminder_enabled=True,
                reminder_sent_at__isnull=True,
                starts_at__gt=now,
            )
            .annotate(whatsapp_due_at=due_expression)
            .filter(whatsapp_due_at__lte=now)
            .order_by("starts_at")
            .values_list("id", flat=True)[:limit]
        )

        sent = 0
        failed = 0
        skipped = 0
        language = "en" if getattr(settings, "WHATSAPP_DEFAULT_LANGUAGE", "ar") == "en" else "ar"

        for appointment_id in candidate_ids:
            try:
                with transaction.atomic():
                    appointment = (
                        Appointment.objects.select_for_update()
                        .select_related("patient")
                        .get(pk=appointment_id)
                    )
                    current_time = timezone.now()
                    if (
                        appointment.status not in ACTIVE_REMINDER_STATUSES
                        or not appointment.reminder_enabled
                        or appointment.reminder_sent_at is not None
                        or appointment.starts_at <= current_time
                        or appointment.reminder_due_at > current_time
                    ):
                        skipped += 1
                        continue
                    if send_appointment_reminder(appointment, language):
                        appointment.reminder_sent_at = timezone.now()
                        appointment.save(update_fields=["reminder_sent_at", "updated_at"])
                        sent += 1
            except WhatsAppConfigurationError as exc:
                raise CommandError("WhatsApp provider configuration is incomplete.") from exc
            except WhatsAppDeliveryError:
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"WhatsApp reminders processed: sent={sent} failed={failed} skipped={skipped}"
            )
        )
