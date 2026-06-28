from apps.core.models import AuditLog


MAX_AUDIT_NOTE_LENGTH = 200


def trim_audit_note(note):
    note = " ".join((note or "").strip().split())
    if len(note) <= MAX_AUDIT_NOTE_LENGTH:
        return note
    return f"{note[: MAX_AUDIT_NOTE_LENGTH - 3]}..."


def appointment_metadata(
    appointment,
    *,
    old_status="",
    new_status="",
    old_starts_at=None,
    new_starts_at=None,
    note="",
    actor=None,
):
    metadata = {
        "appointment_id": appointment.id,
        "public_token": str(appointment.public_token),
    }
    if old_status:
        metadata["old_status"] = old_status
    if new_status:
        metadata["new_status"] = new_status
    if old_starts_at:
        metadata["old_starts_at"] = old_starts_at.isoformat()
    if new_starts_at:
        metadata["new_starts_at"] = new_starts_at.isoformat()
    if actor is not None and getattr(actor, "is_authenticated", False):
        metadata["actor_user_id"] = actor.id
    safe_note = trim_audit_note(note)
    if safe_note:
        metadata["operation_note"] = safe_note
    return metadata


def create_appointment_audit(
    *,
    appointment,
    action,
    message,
    actor=None,
    old_status="",
    new_status="",
    old_starts_at=None,
    new_starts_at=None,
    note="",
):
    return AuditLog.objects.create(
        user=actor if actor is not None and getattr(actor, "is_authenticated", False) else None,
        action=action,
        app_label="booking",
        model_name="Appointment",
        object_id=str(appointment.id),
        object_repr=f"{appointment.confirmation_reference} {appointment.starts_at.isoformat()}",
        message=message,
        metadata=appointment_metadata(
            appointment,
            old_status=old_status,
            new_status=new_status,
            old_starts_at=old_starts_at,
            new_starts_at=new_starts_at,
            note=note,
            actor=actor,
        ),
    )
