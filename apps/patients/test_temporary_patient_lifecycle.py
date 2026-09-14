"""Outage lifecycle regression tests. All identities and clinical content are synthetic."""

import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError
from django.db.models.signals import m2m_changed
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.patients import phone_change, temporary_otp
from apps.patients import test_owner_portal_expansion as propagation_tests
from apps.patients.models import AccountOtpChallenge, AccountPhoneChangeChallenge, Consultation, Patient
from apps.patients.otp import WhatsAppOtpServiceUnavailable
from apps.patients.profile_resolution import PatientProfileConflictError, resolve_authenticated_patient
from apps.patients.test_temporary_otp_mode import TemporaryModeFixture
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord


@override_settings(PATIENT_OTP_TEMPORARY_MODE=True)
class TemporaryProfileRegistrationTests(TemporaryModeFixture):
    def test_full_submitted_name_profile_and_staff_badge_in_both_languages(self):
        name = "Synthetic " + "Patient " * 22
        self.assertEqual(self.register(full_name=name).status_code, 302)
        user = get_user_model().objects.get(username=self.phone)
        patient = Patient.objects.get(user=user)
        self.assertEqual(patient.full_name, name.strip())
        self.assertEqual(patient.phone_e164, self.phone)
        self.assertEqual(patient.phone_raw, self.phone)
        staff = get_user_model().objects.create_user(username="synthetic-lifecycle-staff", is_staff=True)
        staff_client = Client()
        staff_client.force_login(staff)
        for flag in (True, False):
            with self.settings(PATIENT_OTP_TEMPORARY_MODE=flag):
                for language, badge in (("ar", "الهاتف غير موثّق"), ("en", "Unverified phone")):
                    response = staff_client.get(self.url("dashboard_patient_list", language))
                    self.assertContains(response, badge, count=1)
                    self.assertNotContains(response, temporary_otp.UNVERIFIED_GROUP)
                    self.assertEqual([row.pk for row in response.context["patients"]], [patient.pk])
                    self.assertTrue(response.context["patients"][0].phone_unverified)
        self.assertTrue(temporary_otp.is_unverified(user))
        self.assertFalse(AccountOtpChallenge.objects.exists())
        self.assertFalse(AccountPhoneChangeChallenge.objects.exists())
        self.sender.assert_not_called()

    def test_profile_failure_rolls_back_user_patient_and_group(self):
        original = Patient.objects.create

        def fail_after_profile_creation(*args, **kwargs):
            original(*args, **kwargs)
            raise IntegrityError("Synthetic profile failure")

        with patch("apps.patients.profile_resolution.Patient.objects.create", side_effect=fail_after_profile_creation):
            self.assertContains(self.register(), temporary_otp.unavailable_message("en"))
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Patient.objects.exists())
        self.assertFalse(Group.objects.exists())

    def test_populated_permission_free_marker_accepts_another_patient(self):
        self.register()
        self.client.logout()
        self.assertEqual(self.register(phone="+12025550102").status_code, 302)
        self.assertEqual(Patient.objects.count(), 2)
        self.assertEqual(Group.objects.get(name=temporary_otp.UNVERIFIED_GROUP).user_set.count(), 2)

    def test_marker_add_failure_rolls_back_entire_registration(self):
        def fail(sender, action, **kwargs):
            if action == "pre_add":
                raise IntegrityError("Synthetic marker failure")

        through = get_user_model().groups.through
        m2m_changed.connect(fail, sender=through)
        try:
            self.assertContains(self.register(), temporary_otp.unavailable_message("en"))
        finally:
            m2m_changed.disconnect(fail, sender=through)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Patient.objects.exists())
        self.assertFalse(Group.objects.exists())

    def test_shared_resolver_rejects_legacy_raw_phone_without_claiming(self):
        user = get_user_model().objects.create_user(username=self.phone)
        patient = Patient.objects.create(full_name="Synthetic Legacy Patient", phone_raw="+1 (202) 555-0101")
        with self.assertRaises(PatientProfileConflictError):
            resolve_authenticated_patient(user)
        patient.refresh_from_db()
        self.assertIsNone(patient.user_id)
        self.assertEqual(Patient.objects.count(), 1)

    def test_new_patient_immediately_has_staff_record_and_isolated_portal_media_access(self):
        self.register()
        patient = Patient.objects.get()
        visit = VisitRecord.objects.create(patient=patient, visit_reason="Synthetic visible visit", is_visible_to_patient=True)
        note = ClinicalNote.objects.create(patient=patient, visit=visit, body="Synthetic private clinical note")
        media = RecordMedia.objects.create(
            patient=patient, title="Synthetic visible media", media_type=RecordMedia.MediaType.IMAGE,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            file=SimpleUploadedFile("synthetic.jpg", b"synthetic-media", content_type="image/jpeg"),
        )
        portal = self.client.get(self.url("patient_portal_medical_records"))
        self.assertContains(portal, visit.visit_reason)
        self.assertContains(portal, media.title)
        self.assertNotContains(portal, note.body)
        media_url = reverse("patient_portal_medical_record_media_download_en", kwargs={"public_id": media.public_id})
        response = self.client.get(media_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"synthetic-media")
        response.close()
        with self.assertRaises(ValueError):
            _ = media.file.url
        outsider = get_user_model().objects.create_user(username="+12025550199")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(media_url).status_code, 404)
        self.assertNotContains(self.client.get(self.url("patient_portal_medical_records")), visit.visit_reason)
        staff = get_user_model().objects.create_user(username="synthetic-record-staff", is_staff=True)
        self.client.force_login(staff)
        rows = self.client.get(self.url("dashboard_patient_list")).context["patients"]
        self.assertEqual((rows[0].visit_count, rows[0].note_count, rows[0].media_count), (1, 1, 1))
        record = self.client.get(rows[0].record_url)
        for content in (visit.visit_reason, note.body, media.title):
            self.assertContains(record, content)


class TemporaryProfileBackfillTests(TemporaryModeFixture):
    def setUp(self):
        super().setUp()
        self.group = Group.objects.create(name=temporary_otp.UNVERIFIED_GROUP)

    def candidate(self, suffix, **fields):
        user = get_user_model().objects.create_user(
            username=f"+120255501{suffix:02}", first_name="Synthetic Backfill Patient", **fields,
        )
        user.groups.add(self.group)
        return user

    def run_command(self, apply=False):
        output, errors = StringIO(), StringIO()
        call_command("backfill_temporary_patient_profiles", apply=apply, stdout=output, stderr=errors)
        self.assertEqual(errors.getvalue(), "")
        report = json.loads(output.getvalue())
        self.assertTrue(all(type(value) is int for value in report.values()))
        for value in ("Synthetic", "+1202", "patient_id", "user_id", self.group.name):
            self.assertNotIn(value, output.getvalue())
        return report

    def test_eligible_only_dry_run_apply_idempotence_and_counts_only(self):
        eligible = self.candidate(1)
        self.candidate(2, is_active=False)
        self.candidate(3, is_staff=True)
        self.candidate(4, is_superuser=True)
        unmarked = self.candidate(5)
        unmarked.groups.clear()
        linked = self.candidate(6)
        Patient.objects.create(user=linked, full_name="Synthetic Linked Patient", phone_e164=linked.username)
        conflict = self.candidate(7)
        preexisting = Patient.objects.create(full_name="Synthetic Existing Patient", phone_e164=conflict.username)
        legacy = self.candidate(8)
        raw = Patient.objects.create(full_name="Synthetic Legacy Patient", phone_raw="+1 (202) 555-0108")
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=False):
            preview = self.run_command()
            self.assertEqual(preview, dict(candidates=3, created=0, would_create=1,
                                          skipped_conflict=2, skipped_ineligible=0, failed=0))
            self.assertFalse(Patient.objects.filter(user=eligible).exists())
            report = self.run_command(apply=True)
            self.assertEqual(report["created"], 1)
            patient = Patient.objects.get(user=eligible)
            self.assertEqual(patient.full_name, eligible.first_name)
            self.assertEqual(patient.phone_e164, eligible.username)
            self.assertTrue(temporary_otp.is_unverified(eligible))
            self.assertEqual(self.run_command(apply=True)["created"], 0)
            self.assertEqual(Patient.objects.get(user=eligible).pk, patient.pk)
        for user in (conflict, legacy):
            self.assertFalse(Patient.objects.filter(user=user).exists())
        for existing in (preexisting, raw):
            existing.refresh_from_db()
            self.assertIsNone(existing.user_id)
        self.assertEqual(Patient.objects.count(), 4)
        self.assertFalse(AccountOtpChallenge.objects.exists())
        self.assertFalse(AccountPhoneChangeChallenge.objects.exists())
        self.sender.assert_not_called()

    def test_invalid_phone_and_other_owners_are_skipped(self):
        invalid = self.candidate(1)
        invalid.username = "synthetic-invalid-phone"
        invalid.save(update_fields=["username"])
        conflict = self.candidate(2)
        owner = get_user_model().objects.create_user(username="+12025550199")
        existing = Patient.objects.create(user=owner, full_name="Synthetic Owner", phone_e164=conflict.username)
        report = self.run_command(apply=True)
        self.assertEqual(report["skipped_conflict"], 2)
        self.assertEqual(report["created"], 0)
        existing.refresh_from_db()
        self.assertEqual(existing.user_id, owner.pk)

    def test_failure_rolls_back_candidate_and_does_not_print_exception_data(self):
        self.candidate(1)
        original = resolve_authenticated_patient

        def fail(user):
            original(user)
            raise IntegrityError("Synthetic private exception +12025550101")

        with patch("apps.patients.temporary_otp.resolve_authenticated_patient", side_effect=fail):
            self.assertEqual(self.run_command(apply=True)["failed"], 1)
        self.assertFalse(Patient.objects.exists())
        self.assertEqual(self.run_command(apply=True)["created"], 1)


@override_settings(PATIENT_OTP_TEMPORARY_MODE=False)
class TemporaryPhoneVerificationTests(TemporaryModeFixture):
    new_phone = "+12025550102"

    def setUp(self):
        super().setUp()
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=True):
            self.register()
        self.user = get_user_model().objects.get(username=self.phone)
        self.patient = Patient.objects.get(user=self.user)
        self.original_patient = Patient.objects.values().get(pk=self.patient.pk)
        self.consultation = Consultation.objects.create(patient=self.patient, question="Synthetic clinical history")

    def start(self, current=True):
        if current:
            return phone_change.start_current_phone_verification(user=self.user, language="en")
        return phone_change.start_account_phone_change(
            user=self.user, phone_raw=self.new_phone, phone_e164=self.new_phone, language="en",
        )

    def verify(self, challenge, code=None):
        return phone_change.verify_account_phone_change(
            user=self.user, challenge_id=challenge.public_id,
            code=code if code is not None else self.sender.call_args.args[1],
        )

    def assert_unchanged(self):
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, self.phone)
        self.assertTrue(temporary_otp.is_unverified(self.user))
        self.assertEqual(Patient.objects.values().get(pk=self.patient.pk), self.original_patient)
        self.consultation.refresh_from_db()
        self.assertEqual(self.consultation.patient_id, self.patient.pk)

    def test_current_phone_success_preserves_entire_patient_and_removes_dashboard_badge(self):
        challenge = self.start()
        self.sender.assert_called_once_with(self.phone, self.sender.call_args.args[1], "en")
        self.assert_unchanged()
        self.assertTrue(self.verify(challenge).succeeded)
        self.assertFalse(temporary_otp.is_unverified(self.user))
        self.assertEqual(Patient.objects.values().get(pk=self.patient.pk), self.original_patient)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertFalse(self.verify(challenge).succeeded)
        staff = get_user_model().objects.create_user(username="synthetic-verified-staff", is_staff=True)
        self.client.force_login(staff)
        for language, badge in (("ar", "الهاتف غير موثّق"), ("en", "Unverified phone")):
            self.assertNotContains(self.client.get(self.url("dashboard_patient_list", language)), badge)

    def test_current_phone_ui_and_real_verification_in_both_languages(self):
        for language, label in (("ar", "تأكيد رقم الهاتف"), ("en", "Verify phone number")):
            with self.subTest(language=language):
                group = Group.objects.get(name=temporary_otp.UNVERIFIED_GROUP)
                self.user.groups.add(group)
                cache.clear()
                account = self.client.get(self.url("patient_portal_account", language))
                self.assertContains(account, label)
                route = self.url("patient_portal_password_change", language)
                self.assertContains(self.client.get(route), label)
                # Client-supplied target phones are ignored for current-phone verification.
                response = self.client.post(route, {"action": "phone_current_start", "new_phone": self.new_phone})
                self.assertEqual(response.status_code, 302)
                challenge = AccountPhoneChangeChallenge.objects.latest("pk")
                self.assertEqual(challenge.phone_e164, self.phone)
                self.assert_unchanged()
                response = self.client.post(route, {"action": "phone_verify", "challenge_id": challenge.public_id,
                                                    "otp": self.sender.call_args.args[1]})
                self.assertEqual(response.status_code, 302)
                self.assertFalse(temporary_otp.is_unverified(self.user))
                self.assertNotContains(self.client.get(self.url("patient_portal_account", language)),
                                       f'href="{route}#patient-current-phone-title"')

    def test_both_paths_invalid_expired_exhausted_otp_preserve_patient_and_marker(self):
        for current in (True, False):
            for failure in ("invalid", "expired", "attempts"):
                with self.subTest(current=current, failure=failure):
                    challenge = self.start(current)
                    if failure == "expired":
                        challenge.expires_at = timezone.now() - timedelta(seconds=1)
                        challenge.save(update_fields=["expires_at"])
                    if failure == "attempts":
                        for _ in range(challenge.max_attempts):
                            exhausted = self.verify(challenge, code="wrong")
                        self.assertEqual(exhausted.reason, "attempts")
                    result = self.verify(challenge, code="wrong" if failure == "invalid" else None)
                    self.assertFalse(result.succeeded)
                    self.assertEqual(result.reason, "unavailable" if failure == "attempts" else failure)
                    self.assert_unchanged()

    def test_both_paths_sender_failure_and_resend_failure_grant_nothing(self):
        for current in (True, False):
            for failed_sender in (False, RuntimeError("Synthetic sender failure")):
                self.sender.return_value = failed_sender
                self.sender.side_effect = failed_sender if isinstance(failed_sender, Exception) else None
                with self.assertRaises(WhatsAppOtpServiceUnavailable):
                    self.start(current)
                self.assert_unchanged()
                self.assertFalse(AccountPhoneChangeChallenge.objects.exists())
        self.sender.side_effect = None
        self.sender.return_value = True
        challenge = self.start()
        challenge.last_sent_at = timezone.now() - timedelta(seconds=61)
        challenge.save(update_fields=["last_sent_at"])
        self.sender.return_value = False
        with self.assertRaises(WhatsAppOtpServiceUnavailable):
            phone_change.resend_account_phone_change(user=self.user, challenge_id=challenge.public_id, language="en")
        self.assert_unchanged()
        self.assertEqual(AccountPhoneChangeChallenge.objects.count(), 1)

    def test_both_paths_recheck_normalized_and_legacy_conflicts_at_start_and_verification(self):
        for current in (True, False):
            phone = self.phone if current else self.new_phone
            for legacy in (True, False):
                with self.subTest(current=current, legacy=legacy):
                    challenge = self.start(current)
                    conflict = Patient.objects.create(full_name="Synthetic Conflict", phone_raw=phone,
                                                      phone_e164="" if legacy else phone)
                    with self.assertRaises(phone_change.PhoneChangeConflictError):
                        self.start(current)
                    self.assertEqual(self.verify(challenge).reason, "conflict")
                    self.assert_unchanged()
                    conflict.refresh_from_db()
                    self.assertIsNone(conflict.user_id)
                    conflict.delete()

    def test_missing_or_mismatched_profile_fails_closed_without_relinking(self):
        challenge = self.start()
        Patient.objects.filter(pk=self.patient.pk).update(phone_e164=self.new_phone)
        changed = Patient.objects.values().get(pk=self.patient.pk)
        with self.assertRaises(phone_change.PhoneChangeConflictError):
            self.start()
        self.assertEqual(self.verify(challenge).reason, "conflict")
        self.assertEqual(Patient.objects.values().get(pk=self.patient.pk), changed)
        Patient.objects.filter(pk=self.patient.pk).update(user=None, phone_e164=self.phone)
        for current in (True, False):
            with self.assertRaises(phone_change.PhoneChangeConflictError):
                self.start(current)
        self.assertTrue(temporary_otp.is_unverified(self.user))
        self.assertFalse(Patient.objects.filter(user=self.user).exists())

    def test_conflicting_new_user_and_late_conflict_keep_marker(self):
        challenge = self.start(False)
        get_user_model().objects.create_user(username=self.new_phone)
        with self.assertRaises(phone_change.PhoneChangeConflictError):
            self.start(False)
        self.assertEqual(self.verify(challenge).reason, "conflict")
        self.assert_unchanged()

    def test_new_phone_view_requires_password_and_updates_same_profile_after_otp(self):
        route = self.url("patient_portal_password_change")
        data = dict(action="phone_start", new_phone=self.new_phone, current_password="wrong")
        self.client.post(route, data)
        self.assertFalse(AccountPhoneChangeChallenge.objects.exists())
        data["current_password"] = self.password
        self.assertEqual(self.client.post(route, data).status_code, 302)
        challenge = AccountPhoneChangeChallenge.objects.get()
        self.sender.assert_called_once_with(self.new_phone, self.sender.call_args.args[1], "en")
        self.assert_unchanged()
        self.assertEqual(self.client.post(route, dict(action="phone_verify", challenge_id=challenge.public_id,
                                                    otp=self.sender.call_args.args[1])).status_code, 302)
        self.user.refresh_from_db()
        self.patient.refresh_from_db()
        self.assertEqual(self.user.username, self.new_phone)
        self.assertEqual(self.patient.phone_e164, self.new_phone)
        self.assertEqual(self.patient.phone_raw, self.new_phone)
        self.assertEqual(self.patient.user_id, self.user.pk)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.consultation.patient_id, self.patient.pk)
        self.assertFalse(temporary_otp.is_unverified(self.user))

    def test_patient_update_failure_rolls_back_phone_and_marker(self):
        challenge = self.start(False)
        with patch("apps.patients.phone_change._apply_patient_phone_change", side_effect=IntegrityError):
            self.assertEqual(self.verify(challenge).reason, "conflict")
        self.assert_unchanged()

    def test_marker_removal_failure_rolls_back_user_and_patient_changes(self):
        challenge = self.start(False)

        def fail(sender, action, **kwargs):
            if action == "pre_remove":
                raise IntegrityError("Synthetic marker failure")

        through = get_user_model().groups.through
        m2m_changed.connect(fail, sender=through)
        try:
            self.assertEqual(self.verify(challenge).reason, "conflict")
        finally:
            m2m_changed.disconnect(fail, sender=through)
        self.assert_unchanged()

    def test_current_resend_cooldown_and_old_challenge_invalidation(self):
        challenge = self.start()
        with self.assertRaises(phone_change.PhoneChangeChallengeError):
            phone_change.resend_account_phone_change(user=self.user, challenge_id=challenge.public_id, language="en")
        challenge.last_sent_at = timezone.now() - timedelta(seconds=61)
        challenge.save(update_fields=["last_sent_at"])
        replacement = phone_change.resend_account_phone_change(user=self.user, challenge_id=challenge.public_id, language="en")
        self.assert_unchanged()
        self.assertFalse(self.verify(challenge).succeeded)
        self.assertTrue(self.verify(replacement).succeeded)
        self.assertFalse(temporary_otp.is_unverified(self.user))

    def test_auth_csrf_outage_and_rate_limits_cannot_grant_verification(self):
        route = self.url("patient_portal_password_change")
        self.assertEqual(Client().post(route, {"action": "phone_current_start"}).status_code, 302)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        for action in ("phone_current_start", "phone_start", "phone_verify", "phone_resend"):
            self.assertEqual(csrf_client.post(route, {"action": action}).status_code, 403)
        with self.settings(ACCOUNT_PHONE_CHANGE_START_RATE_LIMIT_PER_HOUR=1):
            self.client.post(route, {"action": "phone_current_start"})
            self.client.post(route, {"action": "phone_current_start"})
            self.assertEqual(self.sender.call_count, 1)
        challenge = AccountPhoneChangeChallenge.objects.get()
        with self.settings(ACCOUNT_PHONE_CHANGE_VERIFY_RATE_LIMIT_PER_HOUR=1):
            wrong_code = "111111" if self.sender.call_args.args[1] != "111111" else "222222"
            self.client.post(route, dict(action="phone_verify", challenge_id=challenge.public_id, otp=wrong_code))
            self.client.post(route, dict(action="phone_verify", challenge_id=challenge.public_id,
                                        otp=self.sender.call_args.args[1]))
        self.assert_unchanged()
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=True):
            for action in ("phone_current_start", "phone_start", "phone_verify", "phone_resend"):
                self.assertEqual(self.client.post(route, {"action": action}).status_code, 503)
            self.assertFalse(self.verify(challenge).succeeded)
            with self.assertRaises(WhatsAppOtpServiceUnavailable):
                self.start()
        self.assert_unchanged()

    def test_other_user_cannot_verify_or_resend_challenge(self):
        challenge = self.start()
        other = get_user_model().objects.create_user(username="+12025550199")
        self.assertFalse(phone_change.verify_account_phone_change(
            user=other, challenge_id=challenge.public_id, code=self.sender.call_args.args[1],
        ).succeeded)
        with self.assertRaises(phone_change.PhoneChangeChallengeError):
            phone_change.resend_account_phone_change(user=other, challenge_id=challenge.public_id, language="en")
        self.assert_unchanged()

    def test_normal_account_cannot_use_current_phone_action_or_receive_marker(self):
        normal = get_user_model().objects.create_user(username="+12025550199")
        with self.assertRaises(phone_change.PhoneChangeConflictError):
            phone_change.start_current_phone_verification(user=normal, language="en")
        self.client.force_login(normal)
        self.assertNotContains(self.client.get(self.url("patient_portal_account")), "Verify phone number")
        self.assertFalse(temporary_otp.is_unverified(normal))
        self.assert_unchanged()


@override_settings(PATIENT_OTP_TEMPORARY_MODE=False)
class TemporaryPhonePropagationTests(propagation_tests.AccountPhonePropagationTests):
    """Run the existing propagation/history contracts on marked accounts as well."""

    def setUp(self):
        super().setUp()
        self.user.groups.add(Group.objects.create(name=temporary_otp.UNVERIFIED_GROUP))

    def change_phone(self, propagate):
        self.assertTrue(temporary_otp.is_unverified(self.user))
        challenge = super().change_phone(propagate)
        self.assertFalse(temporary_otp.is_unverified(self.user))
        return challenge
