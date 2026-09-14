"""Temporary outage contracts. All identities, files and medical text are synthetic."""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.booking.models import Appointment
from apps.patients import temporary_otp, transient_services as access
from apps.patients.models import (
    AccountOtpChallenge, AccountPhoneChangeChallenge, AppointmentLinkRecoveryChallenge,
    Consultation, Patient, TransientConsultation, TransientConsultationAttachment,
    TransientConsultationAudioReply, TransientConsultationChallenge,
)
from apps.patients.profile_resolution import resolve_authenticated_patient
from apps.patients.test_expansion import ExpansionTestMixin


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TemporaryModeFixture(TestCase):
    phone = "+12025550101"
    password = "Synthetic-outage-password-781!"

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.sender = Mock(return_value=True)
        directory = TemporaryDirectory(prefix="kbc-temporary-otp-tests-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        override = override_settings(
            PRIVATE_MEDIA_ROOT=self.root, PATIENT_ACCOUNT_OTP_SENDER=self.sender,
            GUEST_CONSULTATION_OTP_SENDER=self.sender,
            ACCOUNT_PHONE_CHANGE_OTP_SENDER=self.sender,
            APPOINTMENT_LINK_RECOVERY_OTP_SENDER=self.sender,
        )
        override.enable()
        self.addCleanup(override.disable)

    def url(self, name, language="en", obj=None):
        if name.startswith("dashboard_"):
            return reverse(name, kwargs={"public_id": obj.public_id} if obj else None) + ("?lang=en" if language == "en" else "?lang=ar")
        return reverse(name + ("_en" if language == "en" else ""),
                       kwargs={"public_id": obj.public_id} if obj else None)

    def register(self, language="en", client=None, **changes):
        data = dict(phone=self.phone, full_name="Synthetic Outage Account",
                    email="synthetic@example.test", password1=self.password, password2=self.password)
        data.update(changes)
        return (client or self.client).post(self.url("patient_portal_register", language), data)

    def upload(self):
        return SimpleUploadedFile("synthetic.pdf", b"%PDF-1.4\nSynthetic content", content_type="application/pdf")

    def enter_guest(self, language="en", client=None):
        response = (client or self.client).post(self.url("guest_consultation_entry", language),
                                              {"action": "send", "phone": "+1 (202) 555-0101"})
        self.assertEqual(response.status_code, 302)

    def submit_guest(self, language="en", **changes):
        data = dict(action="submit", question="Synthetic private guest question",
                    display_name="Synthetic Guest", attachments=[self.upload()])
        data.update(changes)
        return self.client.post(self.url("guest_consultation_entry", language), data)


class DefaultModeTests(TemporaryModeFixture):
    def test_flag_defaults_false(self):
        self.assertFalse(settings.PATIENT_OTP_TEMPORARY_MODE)

    @override_settings(PATIENT_OTP_TEMPORARY_MODE=False)
    def test_registration_and_guest_still_require_real_verification(self):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                cache.clear()
                self.client = Client()
                self.assertEqual(self.register(language).status_code, 302)
                self.assertFalse(get_user_model().objects.exists())
                self.assertTrue(AccountOtpChallenge.objects.filter(purpose="registration").exists())
                self.sender.assert_called_with(self.phone, self.sender.call_args.args[1], language)
                self.assertEqual(self.submit_guest(language).status_code, 403)
                request = RequestFactory().post("/")
                request.session = {access.TEMPORARY_PHONE_KEY: self.phone}
                for service in (access.create_guest_consultation, access.create_unverified_guest_consultation):
                    with self.assertRaises(access.GuestAccessDenied):
                        service(request, question="Synthetic", display_name="", uploaded_files=[], language=language)
                self.assertFalse(TransientConsultation.objects.exists())


@override_settings(PATIENT_OTP_TEMPORARY_MODE=True)
class TemporaryRegistrationTests(TemporaryModeFixture):
    def test_bilingual_registration_login_and_persistent_unverified_marker(self):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                cache.clear()
                self.client = Client()
                response = self.register(language, phone="+1 (202) 555-0101", is_staff="on", is_superuser="on")
                self.assertEqual(response.status_code, 302)
                user = get_user_model().objects.get()
                self.assertEqual(user.username, self.phone)
                self.assertTrue(user.check_password(self.password))
                self.assertFalse(user.is_staff or user.is_superuser)
                self.assertTrue(user.groups.filter(name=temporary_otp.UNVERIFIED_GROUP).exists())
                self.assertFalse(user.get_all_permissions())
                patient = Patient.objects.get(user=user)
                self.assertEqual(patient.full_name, "Synthetic Outage Account")
                self.assertEqual(patient.phone_e164, self.phone)
                self.assertFalse(AccountOtpChallenge.objects.exists())
                self.sender.assert_not_called()
                self.client.logout()
                response = self.client.post(self.url("patient_portal_login", language),
                                            {"phone": self.phone, "password": self.password})
                self.assertEqual(response.status_code, 302)
                with self.settings(PATIENT_OTP_TEMPORARY_MODE=False):
                    self.assertContains(self.client.get(self.url("patient_portal_account", language)),
                                        "رقم الهاتف غير متحقق منه" if language == "ar" else "Phone unverified")
                patient.delete()
                user.delete()

    def test_conflicts_are_neutral_and_never_claim_existing_records(self):
        for language in ("ar", "en"):
            for kind in ("account", "patient", "linked_patient", "legacy_patient"):
                with self.subTest(language=language, kind=kind):
                    cache.clear()
                    user = None
                    patient = None
                    if kind in {"account", "linked_patient"}:
                        user = get_user_model().objects.create_user(
                            username=self.phone if kind == "account" else "synthetic-other-identity")
                    if kind != "account":
                        patient = Patient.objects.create(
                            user=user, full_name="Synthetic existing medical identity",
                            phone_e164="" if kind == "legacy_patient" else self.phone,
                            phone_raw="+1 (202) 555-0101")
                    count = get_user_model().objects.count()
                    patient_count = Patient.objects.count()
                    response = self.register(language)
                    self.assertContains(response, temporary_otp.unavailable_message(language))
                    self.assertNotContains(response, "Synthetic existing medical identity")
                    self.assertEqual(get_user_model().objects.count(), count)
                    self.assertEqual(Patient.objects.count(), patient_count)
                    if patient:
                        patient.refresh_from_db()
                        self.assertEqual(patient.user_id, user.pk if user else None)
                        patient.delete()
                    if user:
                        user.delete()
        self.sender.assert_not_called()

    def test_validation_rate_limits_and_cache_failure_still_fail_closed(self):
        for changes in ({"phone": "bad"}, {"password1": "123", "password2": "123"},
                        {"password2": "mismatch"}, {"full_name": ""}, {"email": "bad"}):
            cache.clear()
            self.assertEqual(self.register(**changes).status_code, 200)
            self.assertFalse(get_user_model().objects.exists())
        with self.settings(PATIENT_PORTAL_REGISTRATION_IP_ATTEMPTS_PER_HOUR=1):
            cache.clear()
            self.register(password1="123", password2="123")
            self.assertContains(self.register(phone="+12025550102"), "Too many attempts")
        with self.settings(PATIENT_PORTAL_REGISTRATION_PHONE_ATTEMPTS_PER_DAY=1):
            cache.clear()
            self.register(password1="123", password2="123")
            self.assertContains(self.register(client=Client()), "Too many attempts")
        with patch("apps.patients.rate_limits.cache.add", side_effect=RuntimeError):
            self.assertContains(self.register(), "Too many attempts")
        self.assertFalse(get_user_model().objects.exists())
        self.sender.assert_not_called()

    def test_transaction_failure_and_privileged_group_do_not_create_account(self):
        with patch("apps.patients.account_otp.create_registration_user", side_effect=IntegrityError):
            self.assertContains(self.register(), temporary_otp.unavailable_message("en"))
        self.assertFalse(Group.objects.filter(name=temporary_otp.UNVERIFIED_GROUP).exists())
        group = Group.objects.create(name=temporary_otp.UNVERIFIED_GROUP)
        group.permissions.add(Permission.objects.first())
        self.assertContains(self.register(), temporary_otp.unavailable_message("en"))
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Patient.objects.exists())

    def test_late_patient_conflict_is_not_claimed_by_profile_resolution(self):
        self.register()
        user = get_user_model().objects.get()
        original = Patient.objects.get(user=user)
        patient = Patient.objects.create(full_name="Synthetic late booking", phone_e164=self.phone)
        self.assertEqual(resolve_authenticated_patient(user), original)
        patient.refresh_from_db()
        self.assertIsNone(patient.user_id)

    def test_stale_registration_otp_actions_do_not_send_or_create(self):
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=False):
            self.register()
        self.sender.reset_mock()
        for action in ("verify", "resend"):
            self.assertEqual(self.client.post(self.url("patient_portal_register"),
                             {"action": action, "otp": "000000"}).status_code, 302)
        self.assertEqual(self.client.get(self.url("patient_portal_register") + "?verify=1").status_code, 302)
        self.assertFalse(get_user_model().objects.exists())
        self.sender.assert_not_called()


@override_settings(PATIENT_OTP_TEMPORARY_MODE=True)
class TemporaryGuestTests(TemporaryModeFixture):
    def test_bilingual_private_submission_receipt_event_and_zero_grants(self):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                cache.clear()
                self.client = Client()
                self.enter_guest(language)
                self.assertContains(self.client.get(self.url("guest_consultation_entry", language)),
                                    "غير متحقق" if language == "ar" else "Phone unverified")
                with patch("apps.notifications.services.deliver_staff_event") as event:
                    with self.captureOnCommitCallbacks(execute=True) as callbacks:
                        response = self.submit_guest(language, phone="+12025550199")
                    self.assertEqual(len(callbacks), 1)
                    event.assert_called_once_with("new-consultation")
                self.assertRedirects(response, self.url("guest_consultation_entry", language), fetch_redirect_response=False)
                guest = TransientConsultation.objects.latest("id")
                self.assertEqual(guest.phone_e164, self.phone)
                self.assertFalse(guest.phone_verified_at_submission)
                self.assertFalse(TransientConsultationChallenge.objects.exists())
                self.assertFalse(Patient.objects.exists())
                self.assertFalse(get_user_model().objects.exists())
                self.assertNotIn(access.TEMPORARY_PHONE_KEY, self.client.session)
                self.assertNotIn(access.SESSION_KEY, self.client.session)
                receipt = self.client.get(response.url)
                self.assertContains(receipt, 'data-guest-state="receipt"')
                for value in (guest.question, guest.display_name, guest.phone_e164, str(guest.public_id)):
                    self.assertNotContains(receipt, value)
                self.assertIn("private", receipt["Cache-Control"])
                self.assertIn("no-store", receipt["Cache-Control"])
                attachment = guest.attachments.get()
                self.assertTrue(attachment.file.storage.exists(attachment.file.name))
                with self.assertRaises(ValueError):
                    _ = attachment.file.url
                author = get_user_model().objects.create_user(username="synthetic-audio-author", is_staff=True)
                audio = TransientConsultationAudioReply.objects.create(created_by=author,
                    consultation=guest, file=SimpleUploadedFile("synthetic.webm", b"synthetic audio", content_type="audio/webm"),
                    content_type="audio/webm", file_size=15)
                for browser in (self.client, Client()):
                    for route, obj in (("guest_consultation_detail", guest),
                                       ("guest_consultation_attachment", attachment), ("guest_consultation_audio", audio)):
                        self.assertEqual(browser.get(self.url(route, language, obj)).status_code, 404)
                    for action in ("send", "resend", "verify", "submit"):
                        self.assertEqual(browser.post(self.url("guest_consultation_detail", language, guest),
                                                      {"action": action, "phone": self.phone}).status_code, 404)
                self.assertEqual(self.submit_guest(language).status_code, 403)
                self.sender.assert_not_called()
                author.delete()

    def test_validation_limits_and_csrf_are_preserved(self):
        self.assertEqual(self.submit_guest().status_code, 403)
        self.assertEqual(self.client.post(self.url("guest_consultation_entry"),
                                         {"action": "send", "phone": "bad"}).status_code, 200)
        self.enter_guest()
        for changes in ({"question": ""}, {"attachments": [self.upload() for _ in range(6)]},
                        {"attachments": [SimpleUploadedFile("synthetic.exe", b"bad")]}):
            self.assertEqual(self.submit_guest(**changes).status_code, 200)
        self.assertFalse(TransientConsultation.objects.exists())
        with self.settings(GUEST_CONSULTATION_SUBMIT_PHONE_PER_HOUR=1):
            cache.clear()
            self.submit_guest(question="")
            self.assertEqual(self.submit_guest().status_code, 429)
        with patch("apps.patients.rate_limits.cache.add", side_effect=RuntimeError):
            self.assertEqual(self.submit_guest().status_code, 429)
        csrf_client = Client(enforce_csrf_checks=True)
        session = csrf_client.session
        session[access.TEMPORARY_PHONE_KEY] = self.phone
        session.save()
        for action in ("send", "submit"):
            self.assertEqual(csrf_client.post(self.url("guest_consultation_entry"),
                                             {"action": action, "phone": self.phone, "question": "Synthetic"}).status_code, 403)
        self.sender.assert_not_called()

    def test_failed_upload_rolls_back_files_rows_and_staff_event(self):
        self.enter_guest()
        original_save = TransientConsultationAttachment.save

        def fail_after_storage(attachment, *args, **kwargs):
            original_save(attachment, *args, **kwargs)
            raise OSError("Synthetic storage failure")

        with patch("apps.patients.models.TransientConsultationAttachment.save", fail_after_storage):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                self.assertEqual(self.submit_guest().status_code, 200)
        self.assertFalse(callbacks)
        self.assertFalse(TransientConsultation.objects.exists())
        self.assertFalse([p for p in self.root.rglob("*") if p.is_file()])
        self.assertEqual(self.client.session[access.TEMPORARY_PHONE_KEY], self.phone)

    def test_phone_only_state_and_stale_otp_cannot_authorize_private_content(self):
        self.enter_guest()
        self.submit_guest()
        guest = TransientConsultation.objects.get()
        attachment = guest.attachments.get()
        cache.clear()
        other = Client()
        self.enter_guest(client=other)
        for route, obj in (("guest_consultation_detail", guest), ("guest_consultation_attachment", attachment)):
            self.assertEqual(other.get(self.url(route, obj=obj)).status_code, 404)
        cache.clear()
        self.client = Client()
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=False):
            self.enter_guest()
        challenge = TransientConsultationChallenge.objects.get()
        self.sender.reset_mock()
        for action in ("verify", "resend"):
            self.assertEqual(self.client.post(self.url("guest_consultation_entry"),
                                             {"action": action, "code": "123456"}).status_code, 403)
        challenge.refresh_from_db()
        self.assertIsNone(challenge.verified_at)
        self.assertIsNone(challenge.grant_expires_at)
        self.sender.assert_not_called()

    def test_rollback_requires_otp_and_discards_unverified_submission_state(self):
        self.enter_guest()
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=False):
            self.assertEqual(self.submit_guest().status_code, 403)
            self.assertNotIn(access.TEMPORARY_PHONE_KEY, self.client.session)
            self.assertContains(self.client.get(self.url("guest_consultation_entry")), "Send WhatsApp code")
        self.assertFalse(TransientConsultation.objects.exists())

    def test_existing_legitimate_grant_still_works_and_later_proof_does_not_relabel_submission(self):
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=False):
            with patch("apps.patients.transient_services.generate_otp_code", return_value="123456"):
                self.enter_guest()
            self.client.post(self.url("guest_consultation_entry"), {"action": "verify", "code": "123456"})
            self.submit_guest()
        guest = TransientConsultation.objects.get()
        self.assertTrue(guest.phone_verified_at_submission)
        self.assertContains(self.client.get(self.url("guest_consultation_detail", obj=guest)), guest.question)
        TransientConsultationChallenge.objects.update(verified_at=guest.created_at + timedelta(seconds=1))
        self.assertFalse(guest.phone_verified_at_submission)


@override_settings(PATIENT_OTP_TEMPORARY_MODE=True)
class TemporarySensitiveFlowTests(TemporaryModeFixture):
    def test_recovery_and_phone_change_get_post_actions_are_neutral(self):
        user = get_user_model().objects.create_user(username=self.phone, password=self.password)
        for language in ("ar", "en"):
            with self.subTest(language=language):
                self.client.force_login(user)
                for route, actions in (
                    ("patient_portal_account_recovery", ("start", "verify", "resend", "reset")),
                    ("patient_portal_link_appointment_recovery", ("start", "verify", "resend", "link", "clear")),
                    ("patient_portal_password_change", ("phone_start", "phone_current_start", "phone_verify", "phone_resend")),
                ):
                    url = self.url(route, language)
                    for action in actions:
                        response = self.client.post(url, {"action": action, "phone": self.phone,
                            "new_phone": "+12025550199", "otp": "123456", "challenge_id": str(uuid4()),
                            "current_password": self.password, "new_password1": "Synthetic-new-pass-901!",
                            "new_password2": "Synthetic-new-pass-901!"})
                        self.assertContains(response, temporary_otp.unavailable_message(language), status_code=503)
                        self.assertNotContains(response, self.phone, status_code=503)
                    if route != "patient_portal_password_change":
                        for query in ("", "?verify=1", "?reset=1"):
                            self.assertEqual(self.client.get(url + query).status_code, 503)
                password_page = self.client.get(self.url("patient_portal_password_change", language))
                self.assertContains(password_page, 'value="password"')
                self.assertNotContains(password_page, 'value="phone_start"')
                for route, hidden in (("patient_portal_account", "patient_portal_account_recovery"),
                                      ("patient_portal_link_appointment", "patient_portal_link_appointment_recovery")):
                    self.assertNotContains(self.client.get(self.url(route, language)), f'href="{self.url(hidden, language)}"')
                self.client.logout()
                self.assertNotContains(self.client.get(self.url("patient_portal_login", language)),
                                       f'href="{self.url("patient_portal_account_recovery", language)}"')
                for phone in (self.phone, "+12025550199"):
                    self.assertContains(self.client.post(self.url("patient_portal_account_recovery", language),
                        {"phone": phone}), temporary_otp.unavailable_message(language), status_code=503)
        user.refresh_from_db()
        self.assertEqual(user.username, self.phone)
        self.assertTrue(user.check_password(self.password))
        for model in (AccountOtpChallenge, AccountPhoneChangeChallenge, AppointmentLinkRecoveryChallenge):
            self.assertFalse(model.objects.exists())
        self.sender.assert_not_called()

    def test_existing_recovery_grant_cannot_reset_during_outage(self):
        user = get_user_model().objects.create_user(username=self.phone, password=self.password)
        with self.settings(PATIENT_OTP_TEMPORARY_MODE=False):
            with patch("apps.patients.account_otp.generate_otp_code", return_value="123456"):
                self.client.post(self.url("patient_portal_account_recovery"), {"phone": self.phone})
            self.client.post(self.url("patient_portal_account_recovery"), {"action": "verify", "otp": "123456"})
        self.sender.reset_mock()
        self.assertIsNotNone(AccountOtpChallenge.objects.get().verified_at)
        response = self.client.post(self.url("patient_portal_account_recovery"),
            {"action": "reset", "new_password1": "Synthetic-new-pass-921!", "new_password2": "Synthetic-new-pass-921!"})
        self.assertEqual(response.status_code, 503)
        user.refresh_from_db()
        self.assertTrue(user.check_password(self.password))
        self.sender.assert_not_called()

    def test_authenticated_password_change_and_csrf_still_work(self):
        for language in ("ar", "en"):
            cache.clear()
            self.client = Client()
            self.register(language)
            user = get_user_model().objects.get()
            response = self.client.post(self.url("patient_portal_password_change", language),
                {"old_password": self.password, "new_password1": "Synthetic-new-pass-921!",
                 "new_password2": "Synthetic-new-pass-921!"})
            self.assertEqual(response.status_code, 302)
            user.refresh_from_db()
            self.assertTrue(user.check_password("Synthetic-new-pass-921!"))
            self.assertEqual(self.client.get(self.url("patient_portal_dashboard", language)).status_code, 200)
            csrf_client = Client(enforce_csrf_checks=True)
            csrf_client.force_login(user)
            self.assertEqual(csrf_client.post(self.url("patient_portal_password_change", language), {}).status_code, 403)
            self.assertEqual(Client(enforce_csrf_checks=True).post(self.url("patient_portal_register", language), {}).status_code, 403)
            user.patient_profile.delete()
            user.delete()
        self.sender.assert_not_called()


@override_settings(PATIENT_OTP_TEMPORARY_MODE=True)
class TemporaryAvailableFlowTests(ExpansionTestMixin, TemporaryModeFixture):
    def test_public_booking_and_staff_push_remain_available(self):
        doctor, visit_type, slot = self.setup_booking()
        with patch("apps.notifications.services.deliver_staff_event") as event:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("booking_confirm"), {
                    "full_name": "Synthetic Anonymous Patient", "phone": self.phone,
                    "same_as_phone": "on", "whatsapp_phone": "", "visit_type": visit_type.pk,
                    "starts_at": slot.value, "booking_note": "Synthetic note",
                })
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Appointment.objects.get().patient.user_id)
        event.assert_called_once_with("new-booking")
        self.sender.assert_not_called()

    def test_authenticated_consultation_ownership_and_staff_dashboard(self):
        self.register()
        user = get_user_model().objects.get()
        with patch("apps.notifications.services.deliver_staff_event") as event:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url("patient_portal_consultation_new"),
                    {"question": "Synthetic registered private question", "attachments": self.upload()})
        self.assertEqual(response.status_code, 302)
        consultation = Consultation.objects.get()
        self.assertEqual(consultation.patient.user_id, user.pk)
        event.assert_called_once_with("new-consultation")
        outsider = Client()
        other = self.create_user(phone="+12025550102")
        outsider.force_login(other)
        for route, obj in (("patient_portal_consultation_detail", consultation),
                           ("patient_portal_consultation_attachment", consultation.attachments.get())):
            self.assertEqual(outsider.get(self.url(route, obj=obj)).status_code, 404)
        guest = TransientConsultation.objects.create(phone_e164=self.phone, question="Synthetic unverified guest")
        staff = self.create_user(phone="synthetic-outage-staff", staff=True)
        self.client.force_login(staff)
        for language in ("ar", "en"):
            self.assertContains(self.client.get(self.url("dashboard_consultation_list", language)),
                                "رقم الهاتف غير متحقق منه" if language == "ar" else "Phone unverified")
            self.assertContains(self.client.get(self.url("dashboard_guest_consultation_detail", language, guest)),
                                "رقم الهاتف غير متحقق منه" if language == "ar" else "Phone unverified")
        self.sender.assert_not_called()
