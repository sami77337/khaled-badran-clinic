"""Small integration hooks that do not change booking domain behavior."""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.whatsapp.booking_notifications import send_booking_confirmation


logger = logging.getLogger(__name__)


def _deliver_booking_confirmation(appointment_id: int) -> None:
    if not getattr(settings, "WHATSAPP_META_ENABLED", False):
        return
    try:
        appointment = Appointment.objects.select_related("patient").get(pk=appointment_id)
        send_booking_confirmation(appointment)
    except Exception:
        # Do not include provider exception text, phone numbers, or payloads.
        logger.warning("WhatsApp booking confirmation delivery unavailable.")


@receiver(post_save, sender=AppointmentStatusHistory, dispatch_uid="kbc_whatsapp_public_booking_confirmation")
def public_booking_confirmation(sender, instance, created, **kwargs):
    if not created or not getattr(settings, "WHATSAPP_META_ENABLED", False):
        return
    if (
        instance.old_status == ""
        and instance.new_status == Appointment.Status.CONFIRMED
        and instance.note == "Created through public booking."
    ):
        transaction.on_commit(lambda: _deliver_booking_confirmation(instance.appointment_id))
