from django.db import transaction
from django.utils import timezone

from apps.patients.models import (
    CONSULTATION_MAX_ATTACHMENTS,
    Consultation,
    ConsultationAttachment,
    validate_consultation_upload,
)
from apps.patients.profile_resolution import resolve_authenticated_patient


@transaction.atomic
def create_consultation(*, user, question, uploaded_files):
    uploaded_files = list(uploaded_files or [])
    if len(uploaded_files) > CONSULTATION_MAX_ATTACHMENTS:
        raise ValueError("Too many consultation attachments.")
    metadata_items = [validate_consultation_upload(item) for item in uploaded_files]
    patient = resolve_authenticated_patient(user)
    consultation = Consultation.objects.create(patient=patient, question=question.strip())
    stored_files = []
    try:
        for uploaded_file, metadata in zip(uploaded_files, metadata_items):
            attachment = ConsultationAttachment(
                consultation=consultation,
                file=uploaded_file,
                **metadata,
            )
            attachment.save()
            stored_files.append((attachment.file.storage, attachment.file.name))
    except Exception:
        for storage, name in stored_files:
            try:
                storage.delete(name)
            except Exception:
                pass
        raise
    return consultation


@transaction.atomic
def update_consultation_reply(*, consultation, staff_user, reply, status):
    locked = Consultation.objects.select_for_update().get(pk=consultation.pk)
    locked.staff_reply = reply.strip()
    locked.status = status
    if locked.staff_reply:
        locked.replied_by = staff_user
        locked.replied_at = timezone.now()
    else:
        locked.replied_by = None
        locked.replied_at = None
    locked.save(
        update_fields=["staff_reply", "status", "replied_by", "replied_at", "updated_at"]
    )
    return locked
