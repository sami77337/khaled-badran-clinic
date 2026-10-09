"""Two existing Django staff categories; use synthetic identities exclusively."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from apps.patients.clinic_roles import (
    CLINIC_DOCTOR_GROUP,
    CLINIC_STAFF_GROUP,
    ROLE_DOCTOR,
    ROLE_STAFF,
    clinic_role,
    may_author_clinical_reply,
)
from apps.patients.models import Patient


class ClinicAccountRoleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.doctor = User.objects.create_user(
            username="synthetic-role-doctor", is_staff=True,
        )
        self.staff = User.objects.create_user(
            username="synthetic-role-staff", is_staff=True,
        )
        self.unassigned = User.objects.create_user(
            username="synthetic-existing-staff", is_staff=True,
        )
        self.patient_user = User.objects.create_user(
            username="synthetic-patient-role",
        )
        self.patient = Patient.objects.create(
            user=self.patient_user, full_name="Synthetic Patient",
        )

    def _assign(self, user, role, **kwargs):
        output = StringIO()
        call_command(
            "assign_clinic_role", user_id=user.pk, role=role,
            stdout=output, **kwargs,
        )
        return output.getvalue()

    def test_staff_login_copy_is_bilingual(self):
        for route, text in (
            ("login", "الطبيب / الطاقم"),
            ("login_en", "Doctor / Staff"),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route), {"role": "doctor"})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, text)
                self.assertContains(response, 'data-auth-role="doctor"')

    def test_migration_creates_two_distinct_groups_without_assigning_users(self):
        doctor = Group.objects.get(name=CLINIC_DOCTOR_GROUP)
        staff = Group.objects.get(name=CLINIC_STAFF_GROUP)
        codes = set(doctor.permissions.values_list("codename", flat=True))
        self.assertIn("change_consultation", codes)
        self.assertIn("change_transientconsultation", codes)
        self.assertNotIn("change_consultation", staff.permissions.values_list("codename", flat=True))
        self.assertNotIn("change_transientconsultation", staff.permissions.values_list("codename", flat=True))
        self.assertFalse(self.unassigned.groups.filter(
            name__in=(CLINIC_DOCTOR_GROUP, CLINIC_STAFF_GROUP),
        ).exists())
        self.assertIsNone(clinic_role(self.unassigned))
        self.assertFalse(may_author_clinical_reply(self.unassigned))

    def test_dry_run_does_not_change_role_or_staff_flag(self):
        message = self._assign(self.unassigned, ROLE_DOCTOR)
        self.unassigned.refresh_from_db()
        self.assertIn("DRY RUN", message)
        self.assertFalse(self.unassigned.groups.filter(name=CLINIC_DOCTOR_GROUP).exists())
        self.assertIsNone(clinic_role(self.unassigned))
        self.assertNotIn(self.unassigned.username, message)

    def test_doctor_and_staff_have_distinct_clinical_permissions(self):
        self._assign(self.doctor, ROLE_DOCTOR, apply=True)
        self._assign(self.staff, ROLE_STAFF, apply=True)
        self.doctor.refresh_from_db()
        self.staff.refresh_from_db()
        self.assertEqual(clinic_role(self.doctor), ROLE_DOCTOR)
        self.assertEqual(clinic_role(self.staff), ROLE_STAFF)
        self.assertTrue(may_author_clinical_reply(self.doctor))
        self.assertFalse(may_author_clinical_reply(self.staff))
        for permission in (
            "patients.change_consultation",
            "patients.change_transientconsultation",
        ):
            self.assertTrue(self.doctor.has_perm(permission))
            self.assertFalse(self.staff.has_perm(permission))

    def test_switch_to_staff_removes_doctor_group_and_fails_closed(self):
        self._assign(self.doctor, ROLE_DOCTOR, apply=True)
        self._assign(self.doctor, ROLE_STAFF, apply=True)
        self.doctor.refresh_from_db()
        for key in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            self.doctor.__dict__.pop(key, None)
        self.assertEqual(clinic_role(self.doctor), ROLE_STAFF)
        self.assertFalse(self.doctor.has_perm("patients.change_consultation"))
        self.assertFalse(may_author_clinical_reply(self.doctor))
        self.assertEqual(self.doctor.groups.filter(
            name__in=(CLINIC_DOCTOR_GROUP, CLINIC_STAFF_GROUP),
        ).count(), 1)

    def test_patient_and_unverified_accounts_cannot_be_promoted(self):
        with self.assertRaises(CommandError):
            self._assign(self.patient_user, ROLE_DOCTOR, apply=True)
        self.patient_user.refresh_from_db()
        self.assertFalse(self.patient_user.is_staff)
        self.assertFalse(self.patient_user.groups.filter(name=CLINIC_DOCTOR_GROUP).exists())

        unverified = get_user_model().objects.create_user(
            username="synthetic-unverified-role",
        )
        unverified.groups.add(Group.objects.create(name="patient_phone_unverified_temporary"))
        with self.assertRaises(CommandError):
            self._assign(unverified, ROLE_STAFF, apply=True)
        unverified.refresh_from_db()
        self.assertFalse(unverified.is_staff)

    def test_staff_role_rejects_superuser_and_inactive_accounts(self):
        admin = get_user_model().objects.create_superuser(
            username="synthetic-technical-admin",
            password="Synthetic-test-secret-123!",
        )
        with self.assertRaises(CommandError):
            self._assign(admin, ROLE_STAFF, apply=True)
        self.unassigned.is_active = False
        self.unassigned.save(update_fields=["is_active"])
        with self.assertRaises(CommandError):
            self._assign(self.unassigned, ROLE_DOCTOR, apply=True)

    def test_unknown_and_dual_group_roles_do_not_grant_authority(self):
        self.assertIsNone(clinic_role(self.unassigned))
        self._assign(self.staff, ROLE_STAFF, apply=True)
        self.staff.groups.add(Group.objects.get(name=CLINIC_DOCTOR_GROUP))
        self.assertIsNone(clinic_role(self.staff))
        self.assertFalse(may_author_clinical_reply(self.staff))
        self.staff.is_staff = False
        self.staff.save(update_fields=["is_staff"])
        self.assertIsNone(clinic_role(self.staff))

    def test_role_assignment_refuses_public_accounts_and_creates_no_users(self):
        baseline = get_user_model().objects.count()
        other = get_user_model().objects.create_user(
            username="synthetic-unverified-staff-identity",
        )
        with self.assertRaises(CommandError):
            self._assign(other, ROLE_DOCTOR, apply=True)
        other.refresh_from_db()
        self.assertFalse(other.is_staff)
        self.assertIsNone(clinic_role(other))
        self.assertEqual(get_user_model().objects.count(), baseline + 1)

        output = self._assign(self.unassigned, ROLE_DOCTOR, apply=True)
        self.assertIn("Applied doctor role", output)
        self.assertEqual(get_user_model().objects.count(), baseline + 1)
