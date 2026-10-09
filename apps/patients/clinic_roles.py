"""Two clinic staff account categories using Django's existing groups.

Group membership is explicit; neither public registration nor migration of
existing accounts grants clinical authority.
"""

CLINIC_DOCTOR_GROUP = "KBC Doctor"
CLINIC_STAFF_GROUP = "KBC Clinic Staff"

ROLE_DOCTOR = "doctor"
ROLE_STAFF = "staff"

CLINICAL_CHANGE_CODENAMES = (
    "change_consultation",
    "change_transientconsultation",
)


def clinic_role(user):
    """Return the exclusive clinic role; unknown/conflicting roles fail closed."""
    if (
        user is None
        or not user.is_authenticated
        or not user.is_active
        or not user.is_staff
    ):
        return None

    names = set(
        user.groups.filter(
            name__in=(CLINIC_DOCTOR_GROUP, CLINIC_STAFF_GROUP)
        ).values_list("name", flat=True)
    )
    if names == {CLINIC_DOCTOR_GROUP}:
        return ROLE_DOCTOR
    if names == {CLINIC_STAFF_GROUP}:
        return ROLE_STAFF
    return None


def may_author_clinical_reply(user):
    """Superuser exception and doctor role both need active staff identity."""
    if (
        user is None
        or not user.is_authenticated
        or not user.is_active
        or not user.is_staff
    ):
        return False
    assigned_role = clinic_role(user)
    if assigned_role is not None:
        return assigned_role == ROLE_DOCTOR
    # A conflicting Doctor+Staff assignment fails closed even for superusers.
    if user.groups.filter(
        name__in=(CLINIC_DOCTOR_GROUP, CLINIC_STAFF_GROUP)
    ).exists():
        return False
    return user.is_superuser
