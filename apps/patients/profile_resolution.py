from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.booking.phone import normalize_phone
from apps.patients.models import Patient


PROFILE_CONFLICT_CODE = "existing_patient_requires_link"


class PatientProfileConflictError(ValidationError):
    pass


@transaction.atomic
def resolve_authenticated_patient(user):
    """Resolve a patient profile without claiming a phone-matched medical record."""
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    linked = Patient.objects.select_for_update().filter(user=locked_user).first()
    if linked is not None:
        return linked

    normalized_phone = normalize_phone(locked_user.username)
    conflicts = Patient.objects.select_for_update().filter(phone_e164=normalized_phone)
    if conflicts.exists():
        raise PatientProfileConflictError(
            "An existing patient record must be linked through the secure appointment-link flow.",
            code=PROFILE_CONFLICT_CODE,
        )

    display_name = locked_user.get_full_name().strip() or locked_user.first_name.strip() or "Patient"
    return Patient.objects.create(
        user=locked_user,
        full_name=display_name,
        phone_raw=locked_user.username.strip(),
        phone_e164=normalized_phone,
    )
