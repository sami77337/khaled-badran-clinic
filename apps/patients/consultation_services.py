import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.patients.models import (
    CONSULTATION_MAX_ATTACHMENTS,
    Consultation,
    ConsultationAttachment,
    ConsultationAudioReply,
    ConsultationNotification,
    validate_consultation_audio_upload,
    validate_consultation_upload,
)
from apps.patients.profile_resolution import resolve_authenticated_patient


class ConsultationDeleteError(ValueError):
    pass


class ConsultationAudioStorageError(ValueError):
    pass


logger = logging.getLogger(__name__)


def consultation_has_audio_reply(consultation):
    try:
        return consultation.audio_reply is not None
    except ConsultationAudioReply.DoesNotExist:
        return False


def _delete_replaced_audio_file(storage, name):
    try:
        storage.delete(name)
    except Exception:
        logger.exception("Could not remove a replaced consultation audio file: %s", name)


def patient_can_delete_consultation(consultation, user):
    return bool(
        getattr(user, "is_authenticated", False)
        and consultation.patient.user_id == user.id
        and consultation.status == Consultation.Status.NEW
        and not consultation.staff_reply
        and consultation.replied_at is None
        and consultation.replied_by_id is None
        and consultation.staff_handled_at is None
        and not consultation_has_audio_reply(consultation)
    )


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
        recipient_ids = list(
            get_user_model()
            .objects.filter(is_active=True, is_staff=True)
            .values_list("pk", flat=True)
        )
        ConsultationNotification.objects.bulk_create(
            [
                ConsultationNotification(
                    recipient_id=recipient_id,
                    consultation=consultation,
                    kind=ConsultationNotification.Kind.NEW_CONSULTATION,
                )
                for recipient_id in recipient_ids
            ]
        )
    except Exception:
        for storage, name in stored_files:
            try:
                storage.delete(name)
            except Exception:
                pass
        raise
    return consultation


def update_consultation_reply(
    *,
    consultation,
    staff_user,
    reply,
    status,
    audio_file=None,
    remove_audio=False,
):
    audio_metadata = validate_consultation_audio_upload(audio_file) if audio_file else None
    new_file_reference = None

    try:
        with transaction.atomic():
            locked = (
                Consultation.objects.select_for_update()
                .select_related("patient", "patient__user")
                .get(pk=consultation.pk)
            )
            current_audio = (
                ConsultationAudioReply.objects.select_for_update()
                .filter(consultation=locked)
                .first()
            )
            had_visible_reply = bool(locked.staff_reply.strip()) or current_audio is not None
            old_file_reference = None

            if audio_file:
                if current_audio is None:
                    current_audio = ConsultationAudioReply(
                        consultation=locked,
                        file=audio_file,
                        created_by=staff_user,
                        **audio_metadata,
                    )
                else:
                    if current_audio.file and current_audio.file.name:
                        old_file_reference = (
                            current_audio.file.storage,
                            current_audio.file.name,
                        )
                    current_audio.file = audio_file
                    current_audio.content_type = audio_metadata["content_type"]
                    current_audio.file_size = audio_metadata["file_size"]
                    current_audio.created_by = staff_user

                try:
                    current_audio.save()
                except Exception:
                    if (
                        current_audio.file
                        and current_audio.file.name
                        and getattr(current_audio.file, "_committed", False)
                        and (
                            old_file_reference is None
                            or current_audio.file.name != old_file_reference[1]
                        )
                    ):
                        try:
                            current_audio.file.storage.delete(current_audio.file.name)
                        except Exception:
                            logger.exception(
                                "Could not clean up a failed consultation audio upload: %s",
                                current_audio.file.name,
                            )
                    raise
                new_file_reference = (current_audio.file.storage, current_audio.file.name)

            has_audio_after_save = bool(current_audio) and not (
                remove_audio and audio_file is None
            )
            locked.staff_reply = reply.strip()
            locked.status = status
            if locked.staff_reply or has_audio_after_save:
                locked.replied_by = staff_user
                locked.replied_at = timezone.now()
            else:
                locked.replied_by = None
                locked.replied_at = None
            if locked.staff_handled_at is None:
                locked.staff_handled_at = timezone.now()
            locked.save(
                update_fields=[
                    "staff_reply",
                    "status",
                    "replied_by",
                    "replied_at",
                    "staff_handled_at",
                    "updated_at",
                ]
            )

            if remove_audio and audio_file is None and current_audio is not None:
                if current_audio.file and current_audio.file.name:
                    try:
                        current_audio.file.storage.delete(current_audio.file.name)
                    except Exception as exc:
                        raise ConsultationAudioStorageError(
                            "Consultation audio could not be removed safely."
                        ) from exc
                current_audio.delete()

            has_visible_reply = bool(locked.staff_reply) or has_audio_after_save
            patient_user = locked.patient.user
            if (
                not had_visible_reply
                and has_visible_reply
                and patient_user is not None
            ):
                ConsultationNotification.objects.get_or_create(
                    recipient=patient_user,
                    consultation=locked,
                    kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
                )

            if old_file_reference and old_file_reference != new_file_reference:
                transaction.on_commit(
                    lambda storage=old_file_reference[0], name=old_file_reference[1]: (
                        _delete_replaced_audio_file(storage, name)
                    )
                )
    except Exception:
        if new_file_reference:
            try:
                new_file_reference[0].delete(new_file_reference[1])
            except Exception:
                logger.exception(
                    "Could not clean up rolled-back consultation audio: %s",
                    new_file_reference[1],
                )
        raise
    return locked


@transaction.atomic
def delete_unhandled_consultation(*, user, public_id):
    consultation = (
        Consultation.objects.select_for_update()
        .select_related("patient", "audio_reply")
        .filter(public_id=public_id, patient__user=user)
        .first()
    )
    if consultation is None or not patient_can_delete_consultation(consultation, user):
        raise ConsultationDeleteError("Consultation cannot be deleted.")

    attachments = list(
        ConsultationAttachment.objects.select_for_update()
        .filter(consultation=consultation)
        .order_by("id")
    )
    try:
        for attachment in attachments:
            if attachment.file and attachment.file.name:
                attachment.file.storage.delete(attachment.file.name)
    except Exception:
        raise ConsultationDeleteError("Consultation files could not be deleted safely.") from None

    consultation.delete()
