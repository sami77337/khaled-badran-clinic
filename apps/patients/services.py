from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.booking.models import Appointment
from apps.booking.phone import normalize_phone
from apps.patients.forms import GENERIC_LINK_ERROR
from apps.patients.models import Patient


PATIENT_STATUS_LABELS = {
    Appointment.Status.CONFIRMED: {"ar": "مؤكد", "en": "Confirmed"},
    Appointment.Status.ARRIVED: {"ar": "وصل", "en": "Arrived"},
    Appointment.Status.COMPLETED: {"ar": "مكتمل", "en": "Completed"},
    Appointment.Status.NO_SHOW: {"ar": "فائت", "en": "Missed"},
    Appointment.Status.CANCELLED: {"ar": "ملغي", "en": "Cancelled"},
    Appointment.Status.RESCHEDULED: {"ar": "أعيدت جدولة الموعد", "en": "Rescheduled"},
}


@dataclass(frozen=True)
class PortalAppointment:
    appointment: Appointment
    status_label: str


@dataclass(frozen=True)
class AppointmentLinkResult:
    appointment: Appointment
    already_linked: bool = False


def patient_status_label(status, language="ar"):
    language = "en" if language == "en" else "ar"
    labels = PATIENT_STATUS_LABELS.get(status)
    if not labels:
        return str(status).replace("_", " ").title()
    return labels[language]


def patient_display_name(user):
    profile = getattr(user, "patient_profile", None)
    if profile and profile.full_name:
        return profile.full_name
    full_name = user.get_full_name().strip()
    if full_name:
        return full_name
    if user.email:
        return user.email
    return user.username


def user_patient_profile(user):
    return Patient.objects.filter(user=user).first()


def patient_appointments_queryset(user):
    return (
        Appointment.objects.filter(patient__user=user)
        .select_related("doctor", "patient", "visit_type")
        .order_by("starts_at", "id")
    )


def portal_appointments(user, *, language="ar"):
    return [
        PortalAppointment(
            appointment=appointment,
            status_label=patient_status_label(appointment.status, language),
        )
        for appointment in patient_appointments_queryset(user)
    ]


def upcoming_and_recent_appointments(user, *, language="ar", upcoming_limit=5, recent_limit=5):
    now = timezone.now()
    queryset = patient_appointments_queryset(user)
    upcoming = queryset.filter(starts_at__gte=now).order_by("starts_at", "id")[:upcoming_limit]
    recent = queryset.filter(starts_at__lt=now).order_by("-starts_at", "-id")[:recent_limit]
    return {
        "upcoming": [
            PortalAppointment(appointment=item, status_label=patient_status_label(item.status, language))
            for item in upcoming
        ],
        "recent": [
            PortalAppointment(appointment=item, status_label=patient_status_label(item.status, language))
            for item in recent
        ],
    }


def _patient_normalized_phone(patient):
    if patient.phone_e164:
        return patient.phone_e164
    return normalize_phone(patient.phone_raw)


@transaction.atomic
def link_appointment_to_user(*, user, public_token, normalized_phone):
    try:
        appointment = (
            Appointment.objects.select_for_update()
            .select_related("patient", "doctor", "visit_type")
            .get(public_token=public_token)
        )
    except Appointment.DoesNotExist as exc:
        raise ValidationError(GENERIC_LINK_ERROR) from exc

    patient = appointment.patient
    try:
        patient_phone = _patient_normalized_phone(patient)
    except ValidationError as exc:
        raise ValidationError(GENERIC_LINK_ERROR) from exc

    if patient_phone != normalized_phone:
        raise ValidationError(GENERIC_LINK_ERROR)

    if patient.user_id is not None:
        if patient.user_id == user.id:
            return AppointmentLinkResult(appointment=appointment, already_linked=True)
        raise ValidationError(GENERIC_LINK_ERROR)

    existing_profile = user_patient_profile(user)
    if existing_profile is not None and existing_profile.id != patient.id:
        raise ValidationError(GENERIC_LINK_ERROR)

    update_fields = ["user", "updated_at"]
    patient.user = user
    if not patient.phone_e164:
        patient.phone_e164 = normalized_phone
        update_fields.append("phone_e164")
    patient.save(update_fields=update_fields)
    return AppointmentLinkResult(appointment=appointment, already_linked=False)
