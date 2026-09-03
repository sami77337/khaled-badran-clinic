from datetime import datetime, time, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.booking import services as booking_services
from apps.booking.models import Appointment
from apps.clinic.models import Doctor, DoctorSchedule, VisitType
from apps.core.models import SystemSetting
from apps.patients import phone_change
from apps.patients.models import (
    CONSULTATION_IMAGE_MAX_BYTES,
    AccountPhoneChangeChallenge,
    Consultation,
    ConsultationAttachment,
    Patient,
    safe_upload_basename,
    validate_consultation_upload,
)
from apps.patients.profile_resolution import (
    PatientProfileConflictError,
    resolve_authenticated_patient,
)


class ExpansionTestMixin:
    password = "Synthetic-pass-483!"

    def create_user(self, phone="+962790000101", *, staff=False, name="Synthetic Patient"):
        return get_user_model().objects.create_user(
            username=phone,
            password=self.password,
            first_name=name,
            is_staff=staff,
        )

    def create_patient(self, user=None, phone="+962790000101", name="Synthetic Patient"):
        return Patient.objects.create(
            user=user,
            full_name=name,
            phone_raw=phone,
            phone_e164=phone,
        )

    def setup_booking(self):
        doctor = Doctor.objects.create(
            full_name_ar="طبيب تجريبي",
            full_name_en="Synthetic Doctor",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="تخصص تجريبي",
            specialty_en="Synthetic specialty",
            is_active=True,
        )
        visit_type = VisitType.objects.create(
            doctor=doctor,
            name_ar="زيارة تجريبية",
            name_en="Synthetic visit",
            duration_minutes=30,
            is_active=True,
        )
        day = timezone.localdate() + timedelta(days=1)
        DoctorSchedule.objects.create(
            doctor=doctor,
            weekday=day.weekday(),
            start_time=time(9, 0),
            end_time=time(11, 0),
            is_active=True,
        )
        settings = {
            SystemSetting.BOOKING_ENABLED: ("true", SystemSetting.ValueType.BOOLEAN),
            SystemSetting.BOOKING_MIN_LEAD_MINUTES: ("0", SystemSetting.ValueType.INTEGER),
            SystemSetting.BOOKING_MAX_DAYS_AHEAD: ("30", SystemSetting.ValueType.INTEGER),
            SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES: ("30", SystemSetting.ValueType.INTEGER),
        }
        for key, (value, value_type) in settings.items():
            SystemSetting.objects.create(key=key, value=value, value_type=value_type)
        slot = booking_services.generate_available_slots(
            visit_type=visit_type,
            target_date=day,
            doctor=doctor,
        )[0]
        return doctor, visit_type, slot


class AuthenticatedBookingExpansionTests(ExpansionTestMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.user = self.create_user(phone="+962791234567")
        self.patient = self.create_patient(user=self.user, phone="+962791234567")
        self.doctor, self.visit_type, self.slot = self.setup_booking()

    def test_authenticated_booking_uses_patient_fk_and_separate_phones(self):
        appointment = booking_services.create_public_appointment(
            full_name="Ignored Contact Identity",
            phone_raw="+962795555555",
            whatsapp_phone_raw="+962799999999",
            visit_type_id=self.visit_type.pk,
            starts_at=self.slot.value,
            authenticated_user=self.user,
        )

        appointment.refresh_from_db()
        self.patient.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(appointment.patient, self.patient)
        self.assertEqual(appointment.contact_phone_e164, "+962795555555")
        self.assertEqual(appointment.whatsapp_phone_e164, "+962799999999")
        self.assertEqual(self.patient.phone_e164, "+962791234567")
        self.assertEqual(self.user.username, "+962791234567")
        self.assertEqual(Patient.objects.count(), 1)

    def test_same_as_contact_saves_matching_whatsapp(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patient_portal_book"),
            {
                "visit_type": self.visit_type.pk,
                "starts_at": self.slot.value,
                "booking_note": "Synthetic booking note",
                "contact_phone": "+962795555555",
                "same_as_contact": "on",
                "whatsapp_phone": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.whatsapp_phone_e164, appointment.contact_phone_e164)
        self.assertEqual(appointment.patient, self.patient)

    def test_logged_in_public_booking_preserves_authenticated_owner(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("booking_confirm"),
            {
                "full_name": "Different Display Name",
                "phone": "+962795555555",
                "same_as_phone": "on",
                "whatsapp_phone": "",
                "visit_type": self.visit_type.pk,
                "starts_at": self.slot.value,
                "booking_note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.patient, self.patient)
        self.assertEqual(Patient.objects.count(), 1)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.phone_e164, "+962791234567")

    def test_anonymous_booking_still_creates_patient_and_contact_fields(self):
        response = self.client.post(
            reverse("booking_confirm"),
            {
                "full_name": "Anonymous Synthetic Patient",
                "phone": "+962790000202",
                "same_as_phone": "on",
                "whatsapp_phone": "",
                "visit_type": self.visit_type.pk,
                "starts_at": self.slot.value,
                "booking_note": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.contact_phone_e164, "+962790000202")
        self.assertEqual(appointment.whatsapp_phone_e164, "+962790000202")
        self.assertIsNone(appointment.patient.user)

    def test_legacy_phone_fallbacks(self):
        appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            visit_type=self.visit_type,
            starts_at=self.slot.starts_at,
            ends_at=self.slot.ends_at,
        )
        self.patient.whatsapp_phone_e164 = "+962790000303"
        self.patient.save(update_fields=["whatsapp_phone_e164"])
        self.assertEqual(appointment.effective_contact_phone, "+962791234567")
        self.assertEqual(appointment.effective_whatsapp_phone, "+962790000303")

    def test_authenticated_booking_is_visible_without_link_flow(self):
        appointment = booking_services.create_public_appointment(
            full_name="Synthetic Patient",
            phone_raw="+962790000404",
            visit_type_id=self.visit_type.pk,
            starts_at=self.slot.value,
            authenticated_user=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("patient_portal_appointment_list"))
        self.assertContains(response, appointment.starts_at.strftime("%Y-%m-%d"))


class SafeProfileResolutionTests(ExpansionTestMixin, TestCase):
    def test_existing_linked_profile_is_used(self):
        user = self.create_user()
        patient = self.create_patient(user=user)
        self.assertEqual(resolve_authenticated_patient(user), patient)

    def test_new_account_without_conflict_creates_linked_profile(self):
        user = self.create_user(phone="+962790000505")
        patient = resolve_authenticated_patient(user)
        self.assertEqual(patient.user, user)
        self.assertEqual(patient.phone_e164, user.username)

    def test_unlinked_same_phone_is_not_claimed_or_duplicated(self):
        user = self.create_user(phone="+962790000606")
        existing = self.create_patient(phone="+962790000606")
        with self.assertRaises(PatientProfileConflictError):
            resolve_authenticated_patient(user)
        existing.refresh_from_db()
        self.assertIsNone(existing.user)
        self.assertEqual(Patient.objects.filter(phone_e164="+962790000606").count(), 1)


class ConsultationExpansionTests(ExpansionTestMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.private_dir = TemporaryDirectory()
        self.override = override_settings(PRIVATE_MEDIA_ROOT=self.private_dir.name)
        self.override.enable()
        self.user_a = self.create_user(phone="+962790000701", name="Synthetic Patient A")
        self.patient_a = self.create_patient(user=self.user_a, phone=self.user_a.username, name="Synthetic Patient A")
        self.user_b = self.create_user(phone="+962790000702", name="Synthetic Patient B")
        self.patient_b = self.create_patient(user=self.user_b, phone=self.user_b.username, name="Synthetic Patient B")
        self.staff = self.create_user(phone="synthetic-staff", staff=True, name="Synthetic Doctor")

    def tearDown(self):
        self.override.disable()
        self.private_dir.cleanup()

    def upload(self, name="synthetic.jpg", content_type="image/jpeg", size=12):
        return SimpleUploadedFile(name, b"x" * size, content_type=content_type)

    def create_consultation_with_attachment(self, patient=None):
        patient = patient or self.patient_a
        consultation = Consultation.objects.create(patient=patient, question="Synthetic consultation question")
        uploaded = self.upload()
        metadata = validate_consultation_upload(uploaded)
        attachment = ConsultationAttachment.objects.create(
            consultation=consultation,
            file=uploaded,
            **metadata,
        )
        return consultation, attachment

    def test_patient_creates_and_lists_own_consultation(self):
        Consultation.objects.create(patient=self.patient_b, question="Other synthetic patient question")
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("patient_portal_consultation_new"),
            {"question": "Synthetic question from patient", "attachments": self.upload()},
        )
        self.assertEqual(response.status_code, 302)
        consultation = Consultation.objects.get(patient=self.patient_a)
        self.assertEqual(consultation.patient, self.patient_a)
        self.assertEqual(consultation.attachments.count(), 1)
        response = self.client.get(reverse("patient_portal_consultation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["consultations"]), 1)

    def test_patient_cannot_view_or_fetch_other_patient_content(self):
        consultation, attachment = self.create_consultation_with_attachment(self.patient_b)
        self.client.force_login(self.user_a)
        detail = self.client.get(
            reverse("patient_portal_consultation_detail", kwargs={"public_id": consultation.public_id})
        )
        media = self.client.get(
            reverse("patient_portal_consultation_attachment", kwargs={"public_id": attachment.public_id})
        )
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(media.status_code, 404)

    def test_anonymous_cannot_access_consultations_or_attachment(self):
        _, attachment = self.create_consultation_with_attachment()
        self.assertEqual(self.client.get(reverse("patient_portal_consultation_list")).status_code, 302)
        self.assertEqual(
            self.client.get(
                reverse("patient_portal_consultation_attachment", kwargs={"public_id": attachment.public_id})
            ).status_code,
            302,
        )

    def test_non_staff_denied_and_staff_can_reply_close_and_read_attachment(self):
        consultation, attachment = self.create_consultation_with_attachment()
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse("dashboard_consultation_list")).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("dashboard_consultation_list")).status_code, 200)
        response = self.client.post(
            reverse("dashboard_consultation_detail", kwargs={"public_id": consultation.public_id}),
            {"staff_reply": "Synthetic staff reply", "status": Consultation.Status.CLOSED},
        )
        self.assertEqual(response.status_code, 302)
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.CLOSED)
        self.assertEqual(consultation.replied_by, self.staff)
        media = self.client.get(
            reverse("dashboard_consultation_attachment", kwargs={"public_id": attachment.public_id})
        )
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media["X-Content-Type-Options"], "nosniff")
        media.close()

    def test_patient_attachment_is_protected_and_not_direct_url(self):
        _, attachment = self.create_consultation_with_attachment()
        with self.assertRaises(ValueError):
            _ = attachment.file.url
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse("patient_portal_consultation_attachment", kwargs={"public_id": attachment.public_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn(str(attachment.public_id), response["Content-Disposition"])
        response.close()
        detail = self.client.get(
            reverse(
                "patient_portal_consultation_detail",
                kwargs={"public_id": attachment.consultation.public_id},
            )
        )
        self.assertNotContains(detail, attachment.file.name)

    def test_missing_physical_file_returns_404(self):
        _, attachment = self.create_consultation_with_attachment()
        attachment.file.storage.delete(attachment.file.name)
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse("patient_portal_consultation_attachment", kwargs={"public_id": attachment.public_id})
        )
        self.assertEqual(response.status_code, 404)

    def test_allowed_image_mp4_and_pdf(self):
        cases = (
            ("synthetic.jpeg", "image/jpeg", "image"),
            ("synthetic.png", "image/png", "image"),
            ("synthetic.webp", "image/webp", "image"),
            ("synthetic.mp4", "video/mp4", "short_video"),
            ("synthetic.pdf", "application/pdf", "pdf"),
        )
        for name, content_type, category in cases:
            with self.subTest(name=name):
                self.assertEqual(validate_consultation_upload(self.upload(name, content_type))["file_category"], category)

    def test_rejects_extension_content_type_empty_and_excessive_size(self):
        invalid = (
            self.upload("synthetic.exe", "application/octet-stream"),
            self.upload("synthetic.jpg", "text/html"),
            self.upload("synthetic.jpg", "image/jpeg", size=0),
            self.upload("synthetic.jpg", "image/jpeg", size=CONSULTATION_IMAGE_MAX_BYTES + 1),
        )
        for uploaded in invalid:
            with self.subTest(name=uploaded.name), self.assertRaises(ValidationError):
                validate_consultation_upload(uploaded)

    def test_max_five_attachments_and_safe_filename(self):
        self.client.force_login(self.user_a)
        uploads = [self.upload(f"synthetic-{index}.pdf", "application/pdf") for index in range(6)]
        response = self.client.post(
            reverse("patient_portal_consultation_new"),
            {"question": "Synthetic question", "attachments": uploads},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Consultation.objects.count(), 0)
        self.assertEqual(safe_upload_basename("../../unsafe/synthetic.pdf"), "synthetic.pdf")
        self.assertEqual(safe_upload_basename("../unsafe/synthetic\n.pdf"), "synthetic_.pdf")

    def test_csrf_protects_submission_and_staff_reply(self):
        consultation = Consultation.objects.create(patient=self.patient_a, question="Synthetic question")
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user_a)
        self.assertEqual(
            csrf_client.post(reverse("patient_portal_consultation_new"), {"question": "Synthetic"}).status_code,
            403,
        )
        csrf_client.force_login(self.staff)
        self.assertEqual(
            csrf_client.post(
                reverse("dashboard_consultation_detail", kwargs={"public_id": consultation.public_id}),
                {"staff_reply": "Synthetic reply", "status": Consultation.Status.ANSWERED},
            ).status_code,
            403,
        )

    def test_english_patient_and_staff_routes_render(self):
        consultation = Consultation.objects.create(patient=self.patient_a, question="Synthetic question")
        self.client.force_login(self.user_a)
        self.assertEqual(self.client.get(reverse("patient_portal_consultation_list_en")).status_code, 200)
        self.assertEqual(
            self.client.get(
                reverse("patient_portal_consultation_detail_en", kwargs={"public_id": consultation.public_id})
            ).status_code,
            200,
        )
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(f"{reverse('dashboard_consultation_list')}?lang=en").status_code, 200)


class AccountPhoneChangeExpansionTests(ExpansionTestMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.user = self.create_user(phone="+962790000801")
        self.patient = self.create_patient(user=self.user, phone=self.user.username)
        self.sent_codes = []
        self.sender_override = override_settings(ACCOUNT_PHONE_CHANGE_OTP_SENDER=self.fake_sender)
        self.sender_override.enable()

    def tearDown(self):
        self.sender_override.disable()

    def fake_sender(self, phone_e164, code, language):
        self.sent_codes.append((phone_e164, code, language))

    def start(self, phone="+962790000802"):
        return phone_change.start_account_phone_change(
            user=self.user,
            phone_raw=phone,
            phone_e164=phone,
            language="en",
        )

    def test_challenge_stores_hash_not_plaintext(self):
        challenge = self.start()
        code = self.sent_codes[-1][1]
        self.assertNotEqual(challenge.otp_digest, code)
        self.assertTrue(check_password(code, challenge.otp_digest))
        self.assertRegex(code, r"^\d{6}$")

    def test_success_atomically_updates_user_and_linked_patient_not_appointment(self):
        doctor, visit_type, slot = self.setup_booking()
        appointment = Appointment.objects.create(
            doctor=doctor,
            patient=self.patient,
            visit_type=visit_type,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            contact_phone_raw="+962790000899",
            contact_phone_e164="+962790000899",
            whatsapp_phone_raw="+962790000898",
            whatsapp_phone_e164="+962790000898",
        )
        challenge = self.start()
        result = phone_change.verify_account_phone_change(
            user=self.user,
            challenge_id=challenge.public_id,
            code=self.sent_codes[-1][1],
        )
        self.assertTrue(result.succeeded)
        self.user.refresh_from_db()
        self.patient.refresh_from_db()
        appointment.refresh_from_db()
        challenge.refresh_from_db()
        self.assertEqual(self.user.username, "+962790000802")
        self.assertEqual(self.patient.phone_e164, "+962790000802")
        self.assertEqual(appointment.contact_phone_e164, "+962790000899")
        self.assertEqual(appointment.whatsapp_phone_e164, "+962790000898")
        self.assertIsNotNone(challenge.consumed_at)

    def test_view_requires_current_password_and_keeps_session_after_success(self):
        self.client.force_login(self.user)
        invalid = self.client.post(
            reverse("patient_portal_password_change"),
            {"action": "phone_start", "current_password": "wrong", "new_phone": "+962790000802"},
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(AccountPhoneChangeChallenge.objects.count(), 0)
        started = self.client.post(
            reverse("patient_portal_password_change"),
            {"action": "phone_start", "current_password": self.password, "new_phone": "+962790000802"},
        )
        self.assertEqual(started.status_code, 302)
        challenge = AccountPhoneChangeChallenge.objects.get()
        verified = self.client.post(
            reverse("patient_portal_password_change"),
            {"action": "phone_verify", "challenge_id": challenge.public_id, "otp": self.sent_codes[-1][1]},
        )
        self.assertEqual(verified.status_code, 302)
        self.assertEqual(self.client.get(reverse("patient_portal_account")).status_code, 200)

    def test_duplicate_user_and_conflicting_patient_are_rejected(self):
        other = self.create_user(phone="+962790000803")
        with self.assertRaises(phone_change.PhoneChangeConflictError):
            phone_change.start_account_phone_change(
                user=self.user,
                phone_raw=other.username,
                phone_e164=other.username,
                language="en",
            )
        self.create_patient(phone="+962790000804", name="Unlinked Synthetic Record")
        with self.assertRaises(phone_change.PhoneChangeConflictError):
            phone_change.start_account_phone_change(
                user=self.user,
                phone_raw="+962790000804",
                phone_e164="+962790000804",
                language="en",
            )

    def test_expiry_and_wrong_code_attempt_limit(self):
        challenge = self.start()
        for _ in range(5):
            result = phone_change.verify_account_phone_change(
                user=self.user,
                challenge_id=challenge.public_id,
                code="000000" if self.sent_codes[-1][1] != "000000" else "999999",
            )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.reason, "attempts")
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempt_count, 5)
        self.assertIsNotNone(challenge.consumed_at)

        expired = self.start("+962790000805")
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])
        result = phone_change.verify_account_phone_change(
            user=self.user,
            challenge_id=expired.public_id,
            code=self.sent_codes[-1][1],
        )
        self.assertEqual(result.reason, "expired")

    def test_resend_invalidates_old_challenge_and_code(self):
        old = self.start()
        old.last_sent_at = timezone.now() - timedelta(seconds=61)
        old.save(update_fields=["last_sent_at"])
        new = phone_change.resend_account_phone_change(
            user=self.user,
            challenge_id=old.public_id,
            language="en",
        )
        old.refresh_from_db()
        self.assertIsNotNone(old.consumed_at)
        self.assertNotEqual(old.public_id, new.public_id)
        self.assertNotEqual(old.otp_digest, new.otp_digest)

    def test_resend_cooldown_is_enforced(self):
        challenge = self.start()
        with self.assertRaises(phone_change.PhoneChangeChallengeError):
            phone_change.resend_account_phone_change(
                user=self.user,
                challenge_id=challenge.public_id,
                language="en",
            )

    def test_final_conflict_recheck_prevents_takeover(self):
        challenge = self.start()
        self.create_patient(phone=challenge.phone_e164, name="Conflicting Synthetic Record")
        result = phone_change.verify_account_phone_change(
            user=self.user,
            challenge_id=challenge.public_id,
            code=self.sent_codes[-1][1],
        )
        self.assertFalse(result.succeeded)
        self.assertEqual(result.reason, "conflict")
        self.user.refresh_from_db()
        self.patient.refresh_from_db()
        self.assertEqual(self.user.username, "+962790000801")
        self.assertEqual(self.patient.phone_e164, "+962790000801")

    def test_success_does_not_change_patient_whatsapp_and_code_is_one_time(self):
        self.patient.whatsapp_phone_raw = "+962790000880"
        self.patient.whatsapp_phone_e164 = "+962790000880"
        self.patient.save(update_fields=["whatsapp_phone_raw", "whatsapp_phone_e164"])
        challenge = self.start()
        code = self.sent_codes[-1][1]
        first = phone_change.verify_account_phone_change(
            user=self.user,
            challenge_id=challenge.public_id,
            code=code,
        )
        second = phone_change.verify_account_phone_change(
            user=first.user,
            challenge_id=challenge.public_id,
            code=code,
        )
        self.assertTrue(first.succeeded)
        self.assertFalse(second.succeeded)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.whatsapp_phone_e164, "+962790000880")

    def test_default_provider_failure_fails_closed_and_never_renders_otp(self):
        self.sender_override.disable()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("patient_portal_password_change"),
            {"action": "phone_start", "current_password": self.password, "new_phone": "+962790000802"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "غير متاحة")
        self.assertEqual(AccountPhoneChangeChallenge.objects.count(), 0)
        self.assertNotContains(response, "000000")
        self.sender_override.enable()


class InternationalPhoneComponentExpansionTests(ExpansionTestMixin, TestCase):
    def setUp(self):
        self.user = self.create_user()
        self.create_patient(user=self.user)
        self.client.force_login(self.user)

    def test_registration_link_booking_and_phone_change_reuse_picker_partial(self):
        self.setup_booking()
        routes = (
            "patient_portal_register",
            "patient_portal_link_appointment",
            "patient_portal_book",
            "patient_portal_password_change",
        )
        self.client.logout()
        registration = self.client.get(reverse("patient_portal_register"))
        self.assertTemplateUsed(registration, "booking/partials/international_phone_field.html")
        login = self.client.get(reverse("patient_portal_login"))
        self.assertTemplateUsed(login, "booking/partials/international_phone_field.html")
        self.client.force_login(self.user)
        for route in routes[1:]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertTemplateUsed(response, "booking/partials/international_phone_field.html")
                self.assertContains(response, "data-booking-phone-control")
