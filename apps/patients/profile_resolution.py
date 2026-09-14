from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.booking.phone import normalize_phone
from apps.patients.models import Patient


PROFILE_CONFLICT_CODE = "existing_patient_requires_link"


class PatientProfileConflictError(ValidationError):
    pass


def assert_profile_phone_available(phone, *, user=None):
    """Reject other identities, including legacy raw-only medical records.

    Callers hold their user lock inside a transaction. A match is a conflict,
    never permission to claim a record.
    """
    phone = normalize_phone(phone)
    # Keep canonical conflict locking, but do not lock every unrelated legacy
    # profile while normalizing its raw phone in Python.
    users = get_user_model().objects.filter(username=phone)
    patients = Patient.objects.all()
    if user is not None:
        users = users.exclude(pk=user.pk)
        patients = patients.exclude(user=user)
    conflict = users.exists() or patients.select_for_update().filter(phone_e164=phone).exists()
    if not conflict:
        for raw in patients.filter(phone_e164="").values_list("phone_raw", flat=True).iterator():
            try:
                conflict = normalize_phone(raw) == phone
            except ValidationError:
                continue
            if conflict:
                break
    if conflict:
        raise PatientProfileConflictError(
            "An existing patient record must be linked through the secure appointment-link flow.",
            code=PROFILE_CONFLICT_CODE,
        )


@transaction.atomic
def resolve_authenticated_patient(user, *, full_name=None):
    """Resolve a patient profile without claiming a phone-matched medical record."""
    locked_user = get_user_model().objects.select_for_update().get(pk=user.pk)
    linked = Patient.objects.select_for_update().filter(user=locked_user).first()
    if linked is not None:
        return linked

    normalized_phone = normalize_phone(locked_user.username)
    assert_profile_phone_available(normalized_phone, user=locked_user)

    display_name = full_name or locked_user.get_full_name().strip() or locked_user.first_name.strip() or "Patient"
    return Patient.objects.create(
        user=locked_user,
        full_name=display_name,
        phone_raw=locked_user.username.strip(),
        phone_e164=normalized_phone,
    )
