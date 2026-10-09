"""Assign one clinic staff category to an existing, verified user account."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.patients.clinic_roles import (
    CLINIC_DOCTOR_GROUP,
    CLINIC_STAFF_GROUP,
    ROLE_DOCTOR,
    ROLE_STAFF,
)
from apps.patients.models import Patient


class Command(BaseCommand):
    help = (
        "Assign an existing account to Doctor or Clinic Staff, dry-run by "
        "default. No passwords or new users are created."
    )

    def add_arguments(self, parser):
        parser.add_argument("--user-id", type=int, required=True)
        parser.add_argument(
            "--role", required=True, choices=(ROLE_DOCTOR, ROLE_STAFF),
        )
        parser.add_argument(
            "--apply", action="store_true",
            help="Apply the audited role change; otherwise report a dry run.",
        )

    def handle(self, *args, **options):
        user_id, role = options["user_id"], options["role"]
        with transaction.atomic():
            User = get_user_model()
            try:
                user = User.objects.select_for_update().get(pk=user_id)
            except User.DoesNotExist:
                raise CommandError("Staff account was not found.") from None

            if not user.is_active:
                raise CommandError("Inactive accounts cannot receive a clinic role.")
            if not user.is_staff:
                raise CommandError(
                    "Only existing staff accounts can receive a clinic role. "
                    "Create a dedicated named staff account first."
                )
            if role == ROLE_STAFF and user.is_superuser:
                raise CommandError(
                    "Remove superuser privileges through the approved "
                    "administrative procedure before assigning Clinic Staff."
                )
            if Patient.objects.filter(user_id=user.pk).exists():
                raise CommandError(
                    "Patient-linked accounts cannot be changed into staff accounts."
                )
            if user.groups.filter(
                name="patient_phone_unverified_temporary"
            ).exists():
                raise CommandError(
                    "Unverified patient accounts cannot receive a clinic role."
                )
            try:
                doctor_group = Group.objects.get(name=CLINIC_DOCTOR_GROUP)
                staff_group = Group.objects.get(name=CLINIC_STAFF_GROUP)
            except Group.DoesNotExist:
                raise CommandError("Clinic account groups are not provisioned.") from None

            if not options["apply"]:
                self.stdout.write(
                    f"DRY RUN: would assign {role} role to one existing account. "
                    "No changes made."
                )
                return

            # Other pre-existing groups and account data remain untouched.
            user.groups.remove(doctor_group, staff_group)
            user.groups.add(doctor_group if role == ROLE_DOCTOR else staff_group)

        self.stdout.write(
            self.style.SUCCESS(
                f"Applied {role} role to one existing account. "
                "No credentials or account identity printed."
            )
        )
