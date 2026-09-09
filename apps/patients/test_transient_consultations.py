"""Synthetic-only guest access, private media and registered-route regressions."""
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.patients.consultation_services import update_consultation_reply
from apps.patients.models import (
    Consultation, Patient, TransientConsultation, TransientConsultationAttachment,
    TransientConsultationAudioReply, TransientConsultationChallenge,
    CONSULTATION_ATTACHMENT_POLICIES,
)
from apps.patients import transient_services as access


class GuestConsultationTests(TestCase):
    phone = "+12025550101"

    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username="synthetic-guest-staff", is_staff=True)
        cls.patient_user = get_user_model().objects.create_user(username="synthetic-guest-patient", password="Synthetic-pass-952!")
        cls.patient = Patient.objects.create(user=cls.patient_user, full_name="Synthetic unrelated patient", phone_e164=cls.phone)
        cls.registered = Consultation.objects.create(patient=cls.patient, question="Synthetic registered secret")

    def setUp(self):
        cache.clear()
        self.directory = TemporaryDirectory(prefix="kbc-guest-tests-")
        self.addCleanup(self.directory.cleanup)
        self.sender = Mock(return_value=True)
        self.settings_override = override_settings(
            PRIVATE_MEDIA_ROOT=self.directory.name, GUEST_CONSULTATION_OTP_SENDER=self.sender,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.codes = patch("apps.patients.transient_services.generate_otp_code", return_value="123456")
        self.codes.start()
        self.addCleanup(self.codes.stop)

    def url(self, name="entry", obj=None, language="en"):
        return reverse("guest_consultation_" + name + ("_en" if language == "en" else ""),
                       kwargs={"public_id": obj.public_id} if obj else None)

    def verify(self, client=None, target=None, phone=None, language="en"):
        client = client or self.client
        url = self.url("detail", target, language) if target else self.url(language=language)
        response = client.post(url, {"action": "send", "phone": phone or self.phone})
        self.assertEqual(response.status_code, 302)
        response = client.post(url, {"action": "verify", "code": "123456"})
        self.assertEqual(response.status_code, 302)
        return response

    def submit(self, client=None, language="en", files=None):
        client = client or self.client
        data = {"action": "submit", "question": "Synthetic guest question secret", "display_name": "Synthetic guest"}
        if files:
            data["attachments"] = files
        response = client.post(self.url(language=language), data)
        self.assertEqual(response.status_code, 302)
        return TransientConsultation.objects.latest("id")

    def guest(self):
        self.verify()
        return self.submit()

    def upload(self, category="image", name=None):
        names = {"image": "synthetic.jpg", "short_video": "synthetic.mp4", "pdf": "synthetic.pdf"}
        types = {"image": "image/jpeg", "short_video": "video/mp4", "pdf": "application/pdf"}
        return SimpleUploadedFile(name or names[category], b"synthetic-content", content_type=types[category])

    def test_bilingual_entry_and_registered_destination(self):
        for language, direction in (("ar", "rtl"), ("en", "ltr")):
            response = self.client.get(self.url(language=language))
            self.assertContains(response, f'lang="{language}" dir="{direction}"')
            self.assertContains(response, "/en/portal/consultations/new/" if language == "en" else "/portal/consultations/new/")
            self.assertIn("private", response["Cache-Control"])
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["Referrer-Policy"], "no-referrer")
            self.assertNotContains(response, 'class="whatsapp-quick-link"')

    def test_otp_required_before_submission(self):
        response = self.client.post(self.url(), {"action": "submit", "question": "Synthetic bypass"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TransientConsultation.objects.exists())

    def test_success_and_no_patient_creation_or_merge_even_matching_phone(self):
        user_count = get_user_model().objects.count()
        guest = self.guest()
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), user_count)
        self.assertFalse(hasattr(guest, "patient_id"))
        self.assertFalse(Consultation._meta.get_field("patient").null)
        self.assertEqual(guest.phone_e164, self.phone)
        self.assertContains(self.client.get(self.url("detail", guest)), "submitted successfully")
        self.assertContains(self.client.get(self.url("detail", guest)), "Awaiting")

    def test_forwarded_url_alone_cannot_read(self):
        guest = self.guest()
        response = Client().get(self.url("detail", guest))
        self.assertContains(response, "Verify to view")
        for secret in (guest.question, guest.display_name, guest.phone_e164):
            self.assertNotContains(response, secret)
        self.assertContains(response, access.masked_phone(self.phone))

    def test_another_verified_guest_cannot_read(self):
        guest = self.guest()
        other = Client()
        self.verify(other, phone="+12025550102")
        self.assertNotContains(other.get(self.url("detail", guest)), guest.question)

    def test_same_phone_entry_grant_does_not_authorize_existing_consultations(self):
        guest = self.guest()
        cache.clear()
        other = Client()
        self.verify(other)
        self.assertNotContains(other.get(self.url("detail", guest)), guest.question)

    def test_later_reverification_is_bound_to_consultation_phone(self):
        guest = self.guest()
        cache.clear()
        other = Client()
        self.verify(other, target=guest, phone="+12025550199")
        self.assertEqual(self.sender.call_args.args[0], self.phone)
        self.assertContains(other.get(self.url("detail", guest)), guest.question)
        self.assertNotContains(other.get(self.url()), 'value="submit"')

    def test_reverified_consultation_cannot_authorize_other_consultation(self):
        guest = self.guest()
        second = TransientConsultation.objects.create(phone_e164=self.phone, question="Synthetic second secret")
        self.assertNotContains(self.client.get(self.url("detail", second)), second.question)

    def test_wrong_otp_denied_and_digest_not_plaintext(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        challenge = TransientConsultationChallenge.objects.get()
        self.assertNotEqual(challenge.otp_digest, "123456")
        response = self.client.post(self.url(), {"action": "verify", "code": "000000"})
        self.assertContains(response, "incorrect")
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempt_count, 1)
        self.assertIsNone(challenge.verified_at)

    def test_expired_otp_denied(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        TransientConsultationChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.client.post(self.url(), {"action": "verify", "code": "123456"})
        self.assertContains(response, "expired")
        self.assertIsNone(TransientConsultationChallenge.objects.get().verified_at)

    def test_attempt_limit_denies_correct_code_after_wrong_attempts(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        for _ in range(5):
            self.client.post(self.url(), {"action": "verify", "code": "000000"})
        self.assertContains(self.client.post(self.url(), {"action": "verify", "code": "123456"}), "incorrect")
        self.assertIsNone(TransientConsultationChallenge.objects.get().verified_at)

    def test_malformed_codes_count_toward_limit(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        self.client.post(self.url(), {"action": "verify", "code": "bad"})
        self.assertEqual(TransientConsultationChallenge.objects.get().attempt_count, 1)

    def test_code_cannot_be_replayed(self):
        self.verify()
        self.assertEqual(self.client.post(self.url(), {"action": "verify", "code": "123456"}).status_code, 403)
        self.assertEqual(TransientConsultationChallenge.objects.get().otp_digest, "")

    def test_challenge_cannot_be_used_by_different_session(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        self.assertEqual(Client().post(self.url(), {"action": "verify", "code": "123456"}).status_code, 403)

    def test_send_phone_cooldown_cannot_be_bypassed_by_new_browser_or_ip(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        response = Client().post(self.url(), {"action": "send", "phone": self.phone}, REMOTE_ADDR="192.0.2.9")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.sender.call_count, 1)

    @override_settings(GUEST_CONSULTATION_SEND_IP_PER_HOUR=1)
    def test_send_ip_limit_for_different_phones(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        self.assertEqual(Client().post(self.url(), {"action": "send", "phone": "+12025550102"}).status_code, 429)

    @override_settings(GUEST_CONSULTATION_VERIFY_IP_PER_HOUR=1)
    def test_verify_rate_limit(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        self.client.post(self.url(), {"action": "verify", "code": "000000"})
        self.assertEqual(self.client.post(self.url(), {"action": "verify", "code": "123456"}).status_code, 429)

    @override_settings(GUEST_CONSULTATION_SUBMIT_PHONE_PER_HOUR=1)
    def test_submission_rate_limit_including_invalid_submissions(self):
        self.verify()
        self.client.post(self.url(), {"action": "submit", "question": ""})
        self.assertEqual(self.client.post(self.url(), {"action": "submit", "question": "Synthetic"}).status_code, 429)

    def test_rate_cache_failure_fails_closed(self):
        with patch("apps.patients.rate_limits.cache.add", side_effect=RuntimeError("Synthetic private failure")):
            with self.assertLogs("apps.patients.transient_services", level="WARNING") as logs:
                response = self.client.post(self.url(), {"action": "send", "phone": self.phone})
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("Synthetic private failure", "".join(logs.output))

    def test_otp_provider_unavailable_no_verification_or_content_logging(self):
        for sender in ("", "invalid.module.sender", Mock(side_effect=RuntimeError(self.phone + " 123456")), Mock(return_value=False)):
            cache.clear()
            with self.settings(GUEST_CONSULTATION_OTP_SENDER=sender):
                with self.assertLogs("apps.patients.transient_services", level="WARNING") as logs:
                    response = self.client.post(self.url(), {"action": "send", "phone": self.phone})
                self.assertContains(response, "currently unavailable")
                self.assertNotIn(self.phone, "".join(logs.output))
                self.assertNotIn("123456", "".join(logs.output))
        self.assertFalse(TransientConsultationChallenge.objects.filter(verified_at__isnull=False).exists())

    def test_resend_invalidates_old_challenge(self):
        self.client.post(self.url(), {"action": "send", "phone": self.phone})
        old = TransientConsultationChallenge.objects.get()
        cache.clear()
        self.client.post(self.url(), {"action": "resend"})
        old.refresh_from_db()
        self.assertIsNotNone(old.revoked_at)

    def test_grant_expiry_requires_reverification_and_denies_files(self):
        guest = self.guest()
        attachment = TransientConsultationAttachment.objects.create(consultation=guest, file=self.upload())
        TransientConsultationChallenge.objects.update(grant_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertNotContains(self.client.get(self.url("detail", guest)), guest.question)
        self.assertEqual(self.client.get(self.url("attachment", attachment)).status_code, 404)

    def test_submission_consumes_entry_grant_and_ignores_posted_phone(self):
        self.verify()
        response = self.client.post(self.url(), {"action": "submit", "question": "Synthetic", "phone": "+12025550199"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TransientConsultation.objects.get().phone_e164, self.phone)
        self.assertEqual(self.client.post(self.url(), {"action": "submit", "question": "Synthetic replay"}).status_code, 403)

    def test_csrf_required_for_phone_otp_submission_and_staff_reply(self):
        csrf = Client(enforce_csrf_checks=True)
        for action in ("send", "verify", "submit"):
            self.assertEqual(csrf.post(self.url(), {"action": action}).status_code, 403)
        guest = self.guest()
        csrf.force_login(self.staff)
        self.assertEqual(csrf.post(reverse("dashboard_guest_consultation_detail", kwargs={"public_id": guest.public_id}), {}).status_code, 403)

    def test_all_attachment_categories_private_and_authorized(self):
        self.verify()
        guest = self.submit(files=[self.upload(category) for category in CONSULTATION_ATTACHMENT_POLICIES])
        self.assertEqual(guest.attachments.count(), 3)
        for attachment in guest.attachments.all():
            response = self.client.get(self.url("attachment", attachment))
            self.assertEqual(response.status_code, 200)
            self.assertIn("private", response["Cache-Control"])
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertNotIn(attachment.original_filename, response["Content-Disposition"])
            response.close()
            self.assertEqual(Client().get(self.url("attachment", attachment)).status_code, 404)
            with self.assertRaises(ValueError):
                _ = attachment.file.url
        html = self.client.get(self.url("detail", guest))
        self.assertNotContains(html, "/media_private/")

    def test_other_verified_guest_cannot_read_attachment_or_voice(self):
        guest = self.guest()
        attachment = TransientConsultationAttachment.objects.create(consultation=guest, file=self.upload())
        audio = TransientConsultationAudioReply.objects.create(consultation=guest, created_by=self.staff,
            file=SimpleUploadedFile("synthetic.webm", b"synthetic", content_type="audio/webm"))
        other = Client()
        self.verify(other, phone="+12025550102")
        for kind, media in (("attachment", attachment), ("audio", audio)):
            self.assertEqual(other.get(self.url(kind, media)).status_code, 404)
            self.assertEqual(Client().get(self.url(kind, media)).status_code, 404)
            response = self.client.get(self.url(kind, media))
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_invalid_attachment_extension_mime_empty_size_and_count(self):
        self.verify()
        invalid = [
            [SimpleUploadedFile("synthetic.html", b"synthetic", content_type="text/html")],
            [SimpleUploadedFile("synthetic.jpg", b"synthetic", content_type="text/html")],
            [SimpleUploadedFile("synthetic.pdf", b"", content_type="application/pdf")],
            [self.upload() for _ in range(6)],
        ]
        for files in invalid:
            response = self.client.post(self.url(), {"action": "submit", "question": "Synthetic", "attachments": files})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
        self.assertFalse(TransientConsultation.objects.exists())
        for category, policy in CONSULTATION_ATTACHMENT_POLICIES.items():
            upload = self.upload(category)
            upload.size = policy["max_bytes"] + 1
            with self.assertRaises(ValidationError):
                TransientConsultationAttachment(file=upload).populate_file_metadata()

    def test_safe_long_filenames_and_escaped_question(self):
        self.verify()
        response = self.client.post(self.url(), {"action": "submit", "question": "<script>synthetic()</script>",
                                               "attachments": self.upload(name="W" * 230 + ".jpg")})
        guest = TransientConsultation.objects.get()
        self.assertEqual(response.status_code, 302)
        response = self.client.get(self.url("detail", guest))
        self.assertNotContains(response, "<script>synthetic()")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotIn("W" * 20, guest.attachments.get().file.name)

    def test_failed_upload_rolls_back_guest_and_preserves_grant(self):
        self.verify()
        original = TransientConsultationAttachment.save
        calls = []
        def failing_save(instance, *args, **kwargs):
            calls.append(instance)
            original(instance, *args, **kwargs)
            if len(calls) == 2:
                raise OSError("Synthetic upload failure")
        with patch.object(TransientConsultationAttachment, "save", failing_save):
            response = self.client.post(self.url(), {"action": "submit", "question": "Synthetic", "attachments": [self.upload(), self.upload()]})
        self.assertContains(response, "could not be saved")
        self.assertFalse(TransientConsultation.objects.exists())
        self.assertIsNone(TransientConsultationChallenge.objects.get().consultation_id)
        self.assertFalse(any(path.is_file() for path in Path(self.directory.name).rglob("*")))

    def test_staff_routes_deny_anonymous_and_patient(self):
        guest = self.guest()
        attachment = TransientConsultationAttachment.objects.create(consultation=guest, file=self.upload())
        audio = TransientConsultationAudioReply.objects.create(consultation=guest, created_by=self.staff,
            file=SimpleUploadedFile("synthetic.webm", b"synthetic", content_type="audio/webm"))
        for route, item in (("detail", guest), ("attachment", attachment), ("audio_reply", audio)):
            url = reverse("dashboard_guest_consultation_" + route, kwargs={"public_id": item.public_id})
            self.assertEqual(Client().get(url).status_code, 302)
            patient_client = Client()
            patient_client.force_login(self.patient_user)
            self.assertEqual(patient_client.get(url).status_code, 403)
            self.assertEqual(patient_client.post(url, {"staff_reply": "Synthetic unauthorized"}).status_code, 403)

    def test_existing_staff_list_distinguishes_guests_and_registered(self):
        guest = self.guest()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard_consultation_list") + "?lang=en")
        self.assertContains(response, "Registered Patient")
        self.assertContains(response, "Guest")
        response = self.client.get(reverse("dashboard_guest_consultation_detail", kwargs={"public_id": guest.public_id}) + "?lang=en")
        self.assertNotContains(response, self.patient.full_name)
        self.assertNotContains(response, self.registered.question)
        self.assertContains(response, "notifications are currently unavailable")

    def test_staff_text_voice_replacement_removal_and_close(self):
        guest = self.guest()
        staff_client = Client()
        staff_client.force_login(self.staff)
        url = reverse("dashboard_guest_consultation_detail", kwargs={"public_id": guest.public_id})
        response = staff_client.post(url, {"status": "answered", "staff_reply": "Synthetic staff reply",
            "audio_reply": SimpleUploadedFile("synthetic.webm", b"synthetic", content_type="audio/webm")})
        self.assertEqual(response.status_code, 302)
        guest.refresh_from_db()
        self.assertEqual(guest.replied_by, self.staff)
        self.assertIsNotNone(guest.staff_handled_at)
        self.assertContains(self.client.get(self.url("detail", guest)), "Synthetic staff reply")
        old = guest.audio_reply.file.name
        with self.captureOnCommitCallbacks(execute=True):
            response = staff_client.post(url, {"status": "answered", "staff_reply": "Synthetic staff reply",
                "audio_reply": SimpleUploadedFile("replacement.ogg", b"synthetic", content_type="audio/ogg")})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(guest.audio_reply.file.storage.exists(old))
        with self.captureOnCommitCallbacks(execute=True):
            staff_client.post(url, {"status": "closed", "staff_reply": "", "remove_audio": "on"})
        self.assertFalse(TransientConsultationAudioReply.objects.filter(consultation=guest).exists())
        self.assertContains(self.client.get(self.url("detail", guest)), "closed without a reply")

    def test_answered_requires_reply_and_rejects_invalid_voice(self):
        guest = self.guest()
        self.client.force_login(self.staff)
        url = reverse("dashboard_guest_consultation_detail", kwargs={"public_id": guest.public_id})
        response = self.client.post(url, {"status": "answered", "staff_reply": "",
            "audio_reply": SimpleUploadedFile("bad.html", b"synthetic", content_type="text/html")})
        self.assertEqual(response.status_code, 200)
        guest.refresh_from_db()
        self.assertEqual(guest.status, "new")
        self.assertFalse(TransientConsultationAudioReply.objects.exists())

    def test_reply_service_requires_active_staff(self):
        guest = self.guest()
        with self.assertRaises(PermissionDenied):
            update_consultation_reply(consultation=guest, staff_user=self.patient_user, reply="Synthetic", status="answered")

    def test_registered_routes_keep_login_return_and_ownership(self):
        for language in ("ar", "en"):
            suffix = "_en" if language == "en" else ""
            new = reverse("patient_portal_consultation_new" + suffix)
            response = Client().get(new)
            self.assertEqual(response.status_code, 302)
            self.assertIn("next=" + new, response.url)
            client = Client()
            client.force_login(self.patient_user)
            self.assertEqual(client.get(new).status_code, 200)
            guest = TransientConsultation.objects.create(phone_e164=self.phone, question="Synthetic isolated guest")
            self.assertEqual(client.get(reverse("patient_portal_consultation_detail" + suffix, kwargs={"public_id": guest.public_id})).status_code, 404)
            other = get_user_model().objects.create_user(username="synthetic-other-" + language)
            client.force_login(other)
            self.assertEqual(client.get(reverse("patient_portal_consultation_detail" + suffix, kwargs={"public_id": self.registered.public_id})).status_code, 404)

    def test_unsafe_next_ignored_in_guest_flow(self):
        self.client.post(self.url() + "?next=https://evil.example/", {"action": "send", "phone": self.phone})
        response = self.client.post(self.url(), {"action": "verify", "code": "123456", "next": "//evil.example/"})
        self.assertEqual(response.url, self.url())

    def test_logout_removes_browser_access(self):
        guest = self.guest()
        self.client.logout()
        self.assertNotContains(self.client.get(self.url("detail", guest)), guest.question)

    def test_staff_can_read_guest_media_but_patient_routes_cannot(self):
        guest = self.guest()
        attachment = TransientConsultationAttachment.objects.create(consultation=guest, file=self.upload())
        client = Client()
        client.force_login(self.staff)
        response = client.get(reverse("dashboard_guest_consultation_attachment", kwargs={"public_id": attachment.public_id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        response.close()
        client.force_login(self.patient_user)
        self.assertEqual(client.get(reverse("patient_portal_consultation_attachment", kwargs={"public_id": attachment.public_id})).status_code, 404)

    def test_postgresql_guest_reply_and_entry_grant_lock_scope(self):
        from apps.patients.test_consultation_locking import ConsultationPostgreSQLLockTests
        self.verify()
        with ConsultationPostgreSQLLockTests.postgres_lock_sql(self) as queries:
            guest = self.submit()
            update_consultation_reply(consultation=guest, staff_user=self.staff, reply="Synthetic", status="answered")
        for model in (TransientConsultationChallenge, TransientConsultation, TransientConsultationAudioReply):
            sql = next(sql for query_model, sql in queries if query_model is model)
            self.assertIn("FOR UPDATE", sql)
            self.assertNotIn('JOIN "patients_patient"', sql)
