from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.booking import services
from apps.booking.audit import create_appointment_audit, trim_audit_note
from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.core.models import AuditLog


TERMINAL_STATUSES = {
    Appointment.Status.COMPLETED,
    Appointment.Status.CANCELLED,
    Appointment.Status.NO_SHOW,
}

ARRIVAL_ALLOWED_FROM = {
    Appointment.Status.CONFIRMED,
    Appointment.Status.RESCHEDULED,
}
CANCELLATION_ALLOWED_FROM = {
    Appointment.Status.CONFIRMED,
    Appointment.Status.ARRIVED,
    Appointment.Status.RESCHEDULED,
}
RESCHEDULE_ALLOWED_FROM = {
    Appointment.Status.CONFIRMED,
    Appointment.Status.RESCHEDULED,
}
NO_SHOW_ALLOWED_FROM = {
    Appointment.Status.CONFIRMED,
    Appointment.Status.RESCHEDULED,
}


def staff_appointment_queryset():
    return Appointment.objects.select_related("doctor", "patient", "visit_type")


def get_staff_appointment(appointment_id, *, for_update=False):
    queryset = staff_appointment_queryset()
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    return queryset.get(id=appointment_id)


def _clean_required_note(note, message):
    note = (note or "").strip()
    if not note:
        raise ValidationError(message)
    return note


def _clean_optional_note(note):
    return (note or "").strip()


def _assert_transition(appointment, allowed_statuses, operation_label):
    if appointment.status in TERMINAL_STATUSES:
        raise ValidationError(f"{operation_label} is not allowed for terminal appointments.")
    if appointment.status not in allowed_statuses:
        raise ValidationError(
            f"{operation_label} is not allowed from {appointment.get_status_display()}."
        )


def _record_status_change(
    appointment,
    *,
    old_status,
    new_status,
    actor=None,
    note="",
    old_starts_at=None,
    new_starts_at=None,
    message,
):
    safe_note = trim_audit_note(note)
    AppointmentStatusHistory.objects.create(
        appointment=appointment,
        old_status=old_status,
        new_status=new_status,
        changed_by=actor if actor is not None and getattr(actor, "is_authenticated", False) else None,
        note=safe_note,
    )
    create_appointment_audit(
        appointment=appointment,
        action=AuditLog.Action.STATUS_CHANGE,
        message=message,
        actor=actor,
        old_status=old_status,
        new_status=new_status,
        old_starts_at=old_starts_at,
        new_starts_at=new_starts_at,
        note=safe_note,
    )


def _save_status_change(appointment, *, new_status, actor=None, note="", message):
    old_status = appointment.status
    old_starts_at = appointment.starts_at
    appointment.status = new_status
    appointment.full_clean()
    appointment.save(update_fields=["status", "updated_at"])
    _record_status_change(
        appointment,
        old_status=old_status,
        new_status=new_status,
        actor=actor,
        note=note,
        old_starts_at=old_starts_at,
        new_starts_at=appointment.starts_at,
        message=message,
    )
    return appointment


@transaction.atomic
def cancel_appointment(appointment_id, *, note, actor=None):
    note = _clean_required_note(note, "Cancellation note is required.")
    appointment = get_staff_appointment(appointment_id, for_update=True)
    _assert_transition(appointment, CANCELLATION_ALLOWED_FROM, "Cancellation")
    return _save_status_change(
        appointment,
        new_status=Appointment.Status.CANCELLED,
        actor=actor,
        note=note,
        message="Appointment cancelled by staff.",
    )


@transaction.atomic
def mark_arrived(appointment_id, *, actor=None, note=""):
    appointment = get_staff_appointment(appointment_id, for_update=True)
    _assert_transition(appointment, ARRIVAL_ALLOWED_FROM, "Mark arrived")
    return _save_status_change(
        appointment,
        new_status=Appointment.Status.ARRIVED,
        actor=actor,
        note=_clean_optional_note(note),
        message="Appointment marked arrived by staff.",
    )


@transaction.atomic
def mark_completed(appointment_id, *, actor=None, note=""):
    appointment = get_staff_appointment(appointment_id, for_update=True)
    _assert_transition(appointment, {Appointment.Status.ARRIVED}, "Completion")
    return _save_status_change(
        appointment,
        new_status=Appointment.Status.COMPLETED,
        actor=actor,
        note=_clean_optional_note(note),
        message="Appointment marked completed by staff.",
    )


@transaction.atomic
def mark_no_show(appointment_id, *, note, actor=None):
    note = _clean_required_note(note, "No-show note is required.")
    appointment = get_staff_appointment(appointment_id, for_update=True)
    _assert_transition(appointment, NO_SHOW_ALLOWED_FROM, "No-show")
    return _save_status_change(
        appointment,
        new_status=Appointment.Status.NO_SHOW,
        actor=actor,
        note=note,
        message="Appointment marked no-show by staff.",
    )


def validate_reschedule_target(appointment, starts_at, *, now=None):
    _assert_transition(appointment, RESCHEDULE_ALLOWED_FROM, "Reschedule")
    if appointment.doctor is None or not appointment.doctor.is_active:
        raise ValidationError("Rescheduling requires an active doctor.")
    if appointment.visit_type is None or not appointment.visit_type.is_active:
        raise ValidationError("Rescheduling requires an active visit type.")

    starts_at = services.parse_slot_datetime(starts_at)
    ends_at = starts_at + timedelta(minutes=appointment.visit_type.duration_minutes)
    if ends_at <= starts_at:
        raise ValidationError("Appointment end time must be after start time.")

    settings = services.get_booking_settings()
    if not services.is_slot_available(
        appointment.visit_type,
        starts_at,
        settings=settings,
        doctor=appointment.doctor,
        now=now,
        exclude_appointment_id=appointment.id,
    ):
        raise ValidationError("This appointment time is not available for rescheduling.")

    if services.overlaps_existing_appointment(
        appointment.doctor,
        starts_at,
        ends_at,
        exclude_appointment_id=appointment.id,
    ):
        raise ValidationError("This appointment overlaps another active appointment.")

    return starts_at, ends_at


@transaction.atomic
def reschedule_appointment(appointment_id, *, starts_at, actor=None, note=""):
    appointment = get_staff_appointment(appointment_id, for_update=True)
    old_status = appointment.status
    old_starts_at = appointment.starts_at
    starts_at, ends_at = validate_reschedule_target(appointment, starts_at)

    appointment.starts_at = starts_at
    appointment.ends_at = ends_at
    appointment.status = Appointment.Status.RESCHEDULED
    appointment.full_clean()
    try:
        appointment.save(update_fields=["starts_at", "ends_at", "status", "updated_at"])
    except IntegrityError as exc:
        raise ValidationError("This appointment time is no longer available.") from exc

    _record_status_change(
        appointment,
        old_status=old_status,
        new_status=Appointment.Status.RESCHEDULED,
        actor=actor,
        note=_clean_optional_note(note),
        old_starts_at=old_starts_at,
        new_starts_at=starts_at,
        message="Appointment rescheduled by staff.",
    )
    return appointment


def restore_appointment(*args, **kwargs):
    raise ValidationError(
        "Restore is intentionally not implemented because terminal states need staff review."
    )
