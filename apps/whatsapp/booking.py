"""Neutral booking delivery using existing appointment state and transactions."""

from functools import partial
import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import DateTimeField, ExpressionWrapper, F
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from apps.booking.models import Appointment
from . import meta
from .webhook import state_key

logger = logging.getLogger(__name__)
UPCOMING_STATUSES = (Appointment.Status.CONFIRMED, Appointment.Status.RESCHEDULED)


def due_reminders(now):
    return (
        Appointment.objects.filter(
            status__in=UPCOMING_STATUSES,
            starts_at__gt=now,
            reminder_enabled=True,
            reminder_sent_at__isnull=True,
        )
        .annotate(
            due_at=ExpressionWrapper(
                F("starts_at") - F("reminder_offset"), output_field=DateTimeField()
            ),
        )
        .filter(due_at__lte=now)
        .order_by("starts_at", "pk")
    )


@sensitive_variables()
def send_due_reminder(appointment_id):
    """Hold the appointment row lock through provider acceptance and timestamp save."""
    with transaction.atomic():
        queryset = due_reminders(timezone.now())
        queryset = queryset.select_for_update(
            skip_locked=connection.features.has_select_for_update_skip_locked
        )
        appointment = queryset.filter(pk=appointment_id).first()
        if appointment is None:
            return "skipped"
        # No patient/model/notes are passed across the provider boundary.
        accepted = meta.send_appointment_notification(
            appointment.effective_whatsapp_phone,
            "APPOINTMENT_REMINDER",
            appointment.starts_at,
            settings.WHATSAPP_DEFAULT_LANGUAGE,
        )
        if accepted is not True:
            return "failed"
        appointment.reminder_sent_at = timezone.now()
        appointment.save(update_fields=["reminder_sent_at", "updated_at"])
        return "sent"


@sensitive_variables()
def send_booking_confirmation(appointment_id, language):
    """Post-commit, best-effort confirmation; failed sends never undo a booking."""
    key = state_key("booking-confirmation", str(appointment_id))
    lock = state_key("booking-confirmation-lock", str(appointment_id))
    acquired = False
    try:
        if cache.get(key):
            return True
        acquired = cache.add(lock, True, timeout=60)
        if not acquired:
            return False
        if cache.get(key):
            return True
        appointment = Appointment.objects.filter(
            pk=appointment_id,
            status__in=UPCOMING_STATUSES,
            starts_at__gt=timezone.now(),
        ).first()
        if appointment is None:
            return False
        accepted = meta.send_appointment_notification(
            appointment.effective_whatsapp_phone,
            "BOOKING_CONFIRMATION",
            appointment.starts_at,
            language,
        )
        if accepted is not True:
            raise ValueError("Delivery unavailable")
        cache.set(key, True, timeout=7 * 86400)
        return True
    except Exception:
        logger.warning(
            "WhatsApp booking confirmation unavailable; saved appointment retained."
        )
        return False
    finally:
        if acquired:
            try:
                cache.delete(lock)
            except Exception:
                pass  # Bounded TTL releases it; never fail the saved booking.


def schedule_booking_confirmation(appointment_id, language):
    if settings.WHATSAPP_META_ENABLED:
        transaction.on_commit(
            partial(send_booking_confirmation, appointment_id, language)
        )
