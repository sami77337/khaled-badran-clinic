"""Synthetic test-only helpers for existing Django clinical model permissions."""

from django.contrib.auth.models import Group, Permission

from apps.patients.clinic_roles import CLINIC_DOCTOR_GROUP


def grant_clinical_reply_permissions(*users):
    permissions = tuple(
        Permission.objects.filter(
            content_type__app_label="patients",
            codename__in=("change_consultation", "change_transientconsultation"),
        )
    )
    if len(permissions) != 2:
        raise AssertionError("Both clinical model permissions must exist.")
    # TransactionTestCase flushes data between methods and does not rerun
    # custom data migrations. Recreate only synthetic test role definitions.
    doctor_role, _created = Group.objects.get_or_create(name=CLINIC_DOCTOR_GROUP)
    doctor_role.permissions.add(*permissions)
    for user in users:
        user.groups.add(doctor_role)
        user.user_permissions.add(*permissions)
        for key in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            user.__dict__.pop(key, None)
