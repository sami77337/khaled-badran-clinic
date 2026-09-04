from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.patients import consultation_services, link_recovery, phone_change
from apps.patients.models import (
    AccountPhoneChangeChallenge,
    AppointmentLinkRecoveryChallenge,
    Consultation,
    ConsultationAttachment,
    Patient,
    validate_consultation_upload,
)
from apps.patients.storage import consultation_attachment_storage


class OwnerExpansionMixin:
    password = "Owner-expansion-pass-843!"

    def create_user(self, phone, *, staff=False):
        return get_user_model().objects.create_user(
            username=phone,
            password=self.password,
            is_staff=staff,
        )

    def create_patient(self, phone, *, user=None, name="Recovery Patient", whatsapp=""):
        return Patient.objects.create(
            user=user,
            full_name=name,
            phone_raw=phone,
            phone_e164=phone,
            whatsapp_phone_raw=whatsapp,
            whatsapp_phone_e164=whatsapp,
        )

    def create_clinic(self):
        doctor = Doctor.objects.create(
            full_name_ar="طبيب الاختبار",
            full_name_en="Owner Test Doctor",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="اختبار",
            specialty_en="Test",
            is_active=True,
        )
        visit_type = VisitType.objects.create(
            doctor=doctor,
            name_ar="زيارة استعادة",
            name_en="Recovery Visit",
            duration_minutes=30,
            is_active=True,
        )
        return doctor, visit_type

    def create_appointment(
        self,
        patient,
        *,
        starts_at=None,
        status=Appointment.Status.CONFIRMED,
        contact="",
        whatsapp="",
        booking_note="",
    ):
        starts_at = starts_at or timezone.now() + timedelta(days=2)
        return Appointment.objects.create(
            doctor=self.doctor,
            patient=patient,
            visit_type=self.visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=status,
            contact_phone_raw=contact,
            contact_phone_e164=contact,
            whatsapp_phone_raw=whatsapp,
            whatsapp_phone_e164=whatsapp,
            booking_note=booking_note,
        )


class AppointmentLinkRecoveryTests(OwnerExpansionMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.user = self.create_user("+962790100001")
        self.doctor, self.visit_type = self.create_clinic()
        self.sent_codes = []
        self.sender_override = override_settings(
            APPOINTMENT_LINK_RECOVERY_OTP_SENDER=self.fake_sender
        )
        self.sender_override.enable()
        self.client.force_login(self.user)

    def tearDown(self):
        self.sender_override.disable()

    def fake_sender(self, phone_e164, code, language):
        self.sent_codes.append((phone_e164, code, language))

    def start(self, phone="+962790100010", language="en"):
        return link_recovery.start_appointment_link_recovery(
            user=self.user,
            phone_raw=phone,
            phone_e164=phone,
            language=language,
        )

    def verify_in_browser(self, challenge):
        return self.client.post(
            reverse("patient_portal_link_appointment_recovery_en"),
            {
                "action": "verify",
                "challenge_id": challenge.public_id,
                "otp": self.sent_codes[-1][1],
            },
        )

    def test_results_require_otp_and_challenge_stores_only_hash(self):
        patient = self.create_patient("+962790100010", name="Never shown before OTP")
        self.create_appointment(patient)
        page = self.client.get(reverse("patient_portal_link_appointment_recovery_en"))
        self.assertNotContains(page, "Recovery Visit")
        challenge = self.start()
        code = self.sent_codes[-1][1]
        self.assertRegex(code, r"^\d{6}$")
        self.assertNotEqual(challenge.otp_digest, code)
        self.assertTrue(check_password(code, challenge.otp_digest))
        self.assertNotContains(page, code)

    def test_wrong_expired_attempt_limit_resend_cooldown_and_one_time_use(self):
        challenge = self.start()
        wrong = "000000" if self.sent_codes[-1][1] != "000000" else "999999"
        for _ in range(5):
            result = link_recovery.verify_appointment_link_recovery(
                user=self.user,
                challenge_id=challenge.public_id,
                code=wrong,
            )
        self.assertEqual(result.reason, "attempts")
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempt_count, 5)
        self.assertIsNotNone(challenge.consumed_at)

        expired = self.start("+962790100011")
        expired.expires_at = timezone.now() - timedelta(seconds=1)
        expired.save(update_fields=["expires_at"])
        result = link_recovery.verify_appointment_link_recovery(
            user=self.user,
            challenge_id=expired.public_id,
            code=self.sent_codes[-1][1],
        )
        self.assertEqual(result.reason, "expired")

        cooling = self.start("+962790100012")
        with self.assertRaises(link_recovery.LinkRecoveryChallengeError):
            link_recovery.resend_appointment_link_recovery(
                user=self.user,
                challenge_id=cooling.public_id,
                language="en",
            )
        code = self.sent_codes[-1][1]
        verified = link_recovery.verify_appointment_link_recovery(
            user=self.user,
            challenge_id=cooling.public_id,
            code=code,
        )
        reused = link_recovery.verify_appointment_link_recovery(
            user=self.user,
            challenge_id=cooling.public_id,
            code=code,
        )
        self.assertTrue(verified.succeeded)
        self.assertFalse(reused.succeeded)

    def test_wrong_otp_is_not_rendered_back(self):
        challenge = self.start()
        wrong = "123456" if self.sent_codes[-1][1] != "123456" else "654321"
        response = self.client.post(
            reverse("patient_portal_link_appointment_recovery_en"),
            {"action": "verify", "challenge_id": challenge.public_id, "otp": wrong},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'value="{wrong}"')

    def test_provider_failure_fails_closed(self):
        self.sender_override.disable()
        response = self.client.post(
            reverse("patient_portal_link_appointment_recovery_en"),
            {"action": "start", "phone": "+962790100010"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "currently unavailable")
        self.assertEqual(AppointmentLinkRecoveryChallenge.objects.count(), 0)
        self.sender_override.enable()

    @override_settings(APPOINTMENT_LINK_RECOVERY_START_RATE_LIMIT_PER_HOUR=1)
    def test_phone_is_normalized_and_start_is_rate_limited(self):
        cache.clear()
        first = self.client.post(
            reverse("patient_portal_link_appointment_recovery_en"),
            {"action": "start", "phone": "0790100010"},
        )
        self.assertEqual(first.status_code, 302)
        challenge = AppointmentLinkRecoveryChallenge.objects.get()
        self.assertEqual(challenge.phone_e164, "+962790100010")
        second = self.client.post(
            reverse("patient_portal_link_appointment_recovery_en"),
            {"action": "start", "phone": "+962790100011"},
        )
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "Too many verification requests")
        self.assertEqual(AppointmentLinkRecoveryChallenge.objects.count(), 1)

    def test_verified_single_patient_links_all_appointments_with_minimum_metadata(self):
        patient = self.create_patient("+962790100010")
        first = self.create_appointment(
            patient,
            contact="+962790100010",
            booking_note="PRIVATE RECOVERY BOOKING NOTE",
        )
        second = self.create_appointment(
            patient,
            starts_at=first.starts_at + timedelta(hours=2),
        )
        Consultation.objects.create(patient=patient, question="PRIVATE MEDICAL QUESTION")
        challenge = self.start()
        self.assertEqual(self.verify_in_browser(challenge).status_code, 302)
        candidates = self.client.get(reverse("patient_portal_link_appointment_recovery_en"))
        self.assertContains(candidates, "Recovery Visit", count=2)
        self.assertContains(candidates, "Link these appointments to my account")
        self.assertNotContains(candidates, "PRIVATE RECOVERY BOOKING NOTE")
        self.assertNotContains(candidates, "PRIVATE MEDICAL QUESTION")
        linked = self.client.post(
            reverse("patient_portal_link_appointment_recovery_en"),
            {"action": "link"},
        )
        self.assertEqual(linked.status_code, 302)
        patient.refresh_from_db()
        self.assertEqual(patient.user, self.user)
        appointment_list = self.client.get(reverse("patient_portal_appointment_list_en"))
        self.assertContains(appointment_list, "Recovery Visit", count=2)

    def test_multiple_patients_conflict_without_identity_exposure_or_merge(self):
        first_patient = self.create_patient(
            "+962790100010", name="CONFLICT IDENTITY ALPHA"
        )
        second_patient = self.create_patient(
            "+962790100010", name="CONFLICT IDENTITY BETA"
        )
        self.create_appointment(first_patient)
        self.create_appointment(
            second_patient,
            starts_at=timezone.now() + timedelta(days=3),
        )
        challenge = self.start()
        self.verify_in_browser(challenge)
        response = self.client.get(reverse("patient_portal_link_appointment_recovery_en"))
        self.assertContains(response, "Contact the clinic")
        self.assertNotContains(response, "CONFLICT IDENTITY ALPHA")
        self.assertNotContains(response, "CONFLICT IDENTITY BETA")
        self.assertNotContains(response, "Link these appointments to my account")
        first_patient.refresh_from_db()
        second_patient.refresh_from_db()
        self.assertIsNone(first_patient.user)
        self.assertIsNone(second_patient.user)

    def test_other_owner_and_existing_different_profile_are_denied(self):
        other = self.create_user("+962790100099")
        owned = self.create_patient("+962790100010", user=other, name="OTHER OWNER")
        self.create_appointment(owned)
        challenge = self.start()
        self.verify_in_browser(challenge)
        response = self.client.get(reverse("patient_portal_link_appointment_recovery_en"))
        self.assertContains(response, "Contact the clinic")
        owned.refresh_from_db()
        self.assertEqual(owned.user, other)

        Appointment.objects.all().delete()
        AppointmentLinkRecoveryChallenge.objects.all().delete()
        self.create_patient(self.user.username, user=self.user, name="Existing Profile")
        unlinked = self.create_patient("+962790100013", name="Unlinked Different Profile")
        self.create_appointment(unlinked)
        challenge = self.start("+962790100013")
        self.verify_in_browser(challenge)
        response = self.client.get(reverse("patient_portal_link_appointment_recovery_en"))
        self.assertContains(response, "Contact the clinic")
        unlinked.refresh_from_db()
        self.assertIsNone(unlinked.user)

    def test_anonymous_denied_and_arabic_english_and_picker_render(self):
        self.client.logout()
        self.assertEqual(
            self.client.get(reverse("patient_portal_link_appointment_recovery")).status_code,
            302,
        )
        self.client.force_login(self.user)
        arabic = self.client.get(reverse("patient_portal_link_appointment_recovery"))
        english = self.client.get(reverse("patient_portal_link_appointment_recovery_en"))
        self.assertContains(arabic, "استعادة ربط المواعيد")
        self.assertContains(english, "Recover Appointment Link")
        self.assertTemplateUsed(arabic, "booking/partials/international_phone_field.html")
        self.assertContains(english, "data-booking-phone-control")

    def test_recovery_posts_enforce_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            reverse("patient_portal_link_appointment_recovery"),
            {"action": "start", "phone": "+962790100010"},
        )
        self.assertEqual(response.status_code, 403)


class ConsultationSafeDeleteTests(OwnerExpansionMixin, TestCase):
    def setUp(self):
        self.private_dir = TemporaryDirectory()
        self.media_override = override_settings(PRIVATE_MEDIA_ROOT=self.private_dir.name)
        self.media_override.enable()
        self.user = self.create_user("+962790200001")
        self.other = self.create_user("+962790200002")
        self.staff = self.create_user("owner-staff", staff=True)
        self.patient = self.create_patient(self.user.username, user=self.user)
        self.other_patient = self.create_patient(self.other.username, user=self.other)

    def tearDown(self):
        self.media_override.disable()
        self.private_dir.cleanup()

    def create_consultation(self, *, patient=None, status=Consultation.Status.NEW):
        return Consultation.objects.create(
            patient=patient or self.patient,
            question="Private consultation body",
            status=status,
        )

    def add_attachment(self, consultation):
        upload = SimpleUploadedFile("private.jpg", b"private-bytes", content_type="image/jpeg")
        return ConsultationAttachment.objects.create(
            consultation=consultation,
            file=upload,
            **validate_consultation_upload(upload),
        )

    def delete_url(self, consultation, *, english=False):
        return reverse(
            "patient_portal_consultation_delete_en"
            if english
            else "patient_portal_consultation_delete",
            kwargs={"public_id": consultation.public_id},
        )

    def test_untouched_own_consultation_and_physical_attachment_are_deleted(self):
        consultation = self.create_consultation()
        attachment = self.add_attachment(consultation)
        storage = attachment.file.storage
        name = attachment.file.name
        self.assertTrue(storage.exists(name))
        self.client.force_login(self.user)
        detail = self.client.get(
            reverse(
                "patient_portal_consultation_detail_en",
                kwargs={"public_id": consultation.public_id},
            )
        )
        self.assertContains(detail, "Delete Consultation")
        confirmation = self.client.get(self.delete_url(consultation, english=True))
        self.assertContains(confirmation, "Confirm Permanent Deletion")
        response = self.client.post(self.delete_url(consultation, english=True))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Consultation.objects.filter(pk=consultation.pk).exists())
        self.assertFalse(ConsultationAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(storage.exists(name))

    def test_cross_patient_anonymous_and_handled_states_are_denied(self):
        other_consultation = self.create_consultation(patient=self.other_patient)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.delete_url(other_consultation)).status_code, 404)
        self.client.logout()
        own = self.create_consultation()
        self.assertEqual(self.client.post(self.delete_url(own)).status_code, 302)

        self.client.force_login(self.user)
        cases = []
        cases.append(self.create_consultation(status=Consultation.Status.ANSWERED))
        cases.append(self.create_consultation(status=Consultation.Status.CLOSED))
        reply = self.create_consultation()
        reply.staff_reply = "Handled"
        reply.save(update_fields=["staff_reply"])
        cases.append(reply)
        replied_at = self.create_consultation()
        replied_at.replied_at = timezone.now()
        replied_at.save(update_fields=["replied_at"])
        cases.append(replied_at)
        replied_by = self.create_consultation()
        replied_by.replied_by = self.staff
        replied_by.save(update_fields=["replied_by"])
        cases.append(replied_by)
        handled = self.create_consultation()
        handled.staff_handled_at = timezone.now()
        handled.save(update_fields=["staff_handled_at"])
        cases.append(handled)
        for item in cases:
            with self.subTest(consultation=item.pk):
                self.assertEqual(self.client.get(self.delete_url(item)).status_code, 404)
                self.assertTrue(Consultation.objects.filter(pk=item.pk).exists())

    def test_staff_action_sets_permanent_handled_timestamp(self):
        consultation = self.create_consultation()
        updated = consultation_services.update_consultation_reply(
            consultation=consultation,
            staff_user=self.staff,
            reply="",
            status=Consultation.Status.CLOSED,
        )
        self.assertIsNotNone(updated.staff_handled_at)
        first_handled_at = updated.staff_handled_at
        updated = consultation_services.update_consultation_reply(
            consultation=updated,
            staff_user=self.staff,
            reply="Updated reply",
            status=Consultation.Status.ANSWERED,
        )
        self.assertEqual(updated.staff_handled_at, first_handled_at)

    def test_storage_failure_preserves_database_state(self):
        consultation = self.create_consultation()
        attachment = self.add_attachment(consultation)
        self.client.force_login(self.user)
        with patch.object(
            consultation_attachment_storage,
            "delete",
            side_effect=OSError("synthetic storage failure"),
        ):
            response = self.client.post(self.delete_url(consultation, english=True))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Consultation.objects.filter(pk=consultation.pk).exists())
        self.assertTrue(ConsultationAttachment.objects.filter(pk=attachment.pk).exists())

    def test_delete_post_enforces_csrf(self):
        consultation = self.create_consultation()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.delete_url(consultation)).status_code, 403)


class AccountPhonePropagationTests(OwnerExpansionMixin, TestCase):
    old_phone = "+962791111111"
    new_phone = "+962792222222"

    def setUp(self):
        self.user = self.create_user(self.old_phone)
        self.patient = self.create_patient(
            self.old_phone,
            user=self.user,
            whatsapp=self.old_phone,
        )
        self.doctor, self.visit_type = self.create_clinic()
        self.sent_codes = []
        self.sender_override = override_settings(
            ACCOUNT_PHONE_CHANGE_OTP_SENDER=self.fake_sender
        )
        self.sender_override.enable()

    def tearDown(self):
        self.sender_override.disable()

    def fake_sender(self, phone_e164, code, language):
        self.sent_codes.append((phone_e164, code, language))

    def change_phone(self, propagate):
        challenge = phone_change.start_account_phone_change(
            user=self.user,
            phone_raw=self.new_phone,
            phone_e164=self.new_phone,
            language="en",
            propagate_to_upcoming_appointments=propagate,
        )
        result = phone_change.verify_account_phone_change(
            user=self.user,
            challenge_id=challenge.public_id,
            code=self.sent_codes[-1][1],
        )
        self.assertTrue(result.succeeded)
        return challenge

    def test_propagation_on_updates_only_old_future_numbers_and_preserves_history(self):
        future_a = self.create_appointment(
            self.patient,
            contact=self.old_phone,
            whatsapp=self.old_phone,
        )
        custom = "+962799999999"
        future_b = self.create_appointment(
            self.patient,
            starts_at=future_a.starts_at + timedelta(hours=2),
            status=Appointment.Status.RESCHEDULED,
            contact=custom,
            whatsapp=custom,
        )
        historical = self.create_appointment(
            self.patient,
            starts_at=timezone.now() - timedelta(days=2),
            contact=self.old_phone,
            whatsapp=self.old_phone,
        )
        consultation = Consultation.objects.create(
            patient=self.patient,
            question="Medical record ownership remains stable",
        )
        patient_id = self.patient.pk
        challenge = self.change_phone(True)
        self.user.refresh_from_db()
        self.patient.refresh_from_db()
        future_a.refresh_from_db()
        future_b.refresh_from_db()
        historical.refresh_from_db()
        consultation.refresh_from_db()
        self.assertTrue(challenge.propagate_to_upcoming_appointments)
        self.assertEqual(self.user.username, self.new_phone)
        self.assertEqual(self.patient.phone_e164, self.new_phone)
        self.assertEqual(self.patient.whatsapp_phone_e164, self.new_phone)
        self.assertEqual(
            (future_a.contact_phone_e164, future_a.whatsapp_phone_e164),
            (self.new_phone, self.new_phone),
        )
        self.assertEqual(
            (future_b.contact_phone_e164, future_b.whatsapp_phone_e164),
            (custom, custom),
        )
        self.assertEqual(
            (historical.contact_phone_e164, historical.whatsapp_phone_e164),
            (self.old_phone, self.old_phone),
        )
        self.assertEqual(self.patient.pk, patient_id)
        self.assertEqual(consultation.patient_id, patient_id)
        self.assertEqual(Patient.objects.count(), 1)

    def test_propagation_off_freezes_legacy_future_fallback_and_preserves_explicit_data(self):
        legacy = self.create_appointment(self.patient)
        explicit = self.create_appointment(
            self.patient,
            starts_at=legacy.starts_at + timedelta(hours=2),
            contact=self.old_phone,
            whatsapp=self.old_phone,
        )
        historical = self.create_appointment(
            self.patient,
            starts_at=timezone.now() - timedelta(days=2),
        )
        challenge = self.change_phone(False)
        self.user.refresh_from_db()
        self.patient.refresh_from_db()
        legacy.refresh_from_db()
        explicit.refresh_from_db()
        historical.refresh_from_db()
        self.assertFalse(challenge.propagate_to_upcoming_appointments)
        self.assertEqual(self.user.username, self.new_phone)
        self.assertEqual(self.patient.phone_e164, self.new_phone)
        self.assertEqual(self.patient.whatsapp_phone_e164, self.old_phone)
        self.assertEqual(
            (legacy.contact_phone_e164, legacy.whatsapp_phone_e164),
            (self.old_phone, self.old_phone),
        )
        self.assertEqual(
            (explicit.contact_phone_e164, explicit.whatsapp_phone_e164),
            (self.old_phone, self.old_phone),
        )
        self.assertEqual(
            (historical.contact_phone_e164, historical.whatsapp_phone_e164),
            ("", ""),
        )

    def test_custom_patient_whatsapp_is_preserved_and_checkbox_defaults_checked(self):
        custom = "+962798888888"
        self.patient.whatsapp_phone_raw = custom
        self.patient.whatsapp_phone_e164 = custom
        self.patient.save(update_fields=["whatsapp_phone_raw", "whatsapp_phone_e164"])
        self.change_phone(True)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.whatsapp_phone_e164, custom)

        second_user = self.create_user("+962793333333")
        self.create_patient(second_user.username, user=second_user)
        self.client.force_login(second_user)
        page = self.client.get(reverse("patient_portal_password_change_en"))
        self.assertContains(page, "Update upcoming appointment contact numbers to the new phone")
        self.assertContains(page, 'name="propagate_to_upcoming_appointments"')
        self.assertContains(page, "checked")
        response = self.client.post(
            reverse("patient_portal_password_change_en"),
            {
                "action": "phone_start",
                "current_password": self.password,
                "new_phone": "+962794444444",
            },
        )
        self.assertEqual(response.status_code, 302)
        stored = AccountPhoneChangeChallenge.objects.filter(user=second_user).get()
        self.assertFalse(stored.propagate_to_upcoming_appointments)
