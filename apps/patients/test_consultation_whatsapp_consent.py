"""Synthetic-only consent and dispatch verification for WhatsApp consultation reply alerts."""

from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.patients import consultation_services
from apps.patients.forms import ConsultationCreateForm
from apps.patients.models import (
    CONSULTATION_WHATSAPP_REPLY_CONSENT_VERSION as VERSION,
    Consultation, Patient, TransientConsultation, TransientConsultationChallenge,
)
from apps.patients.transient_forms import GuestConsultationForm
from apps.whatsapp.notifications import send_reply_notification_if_consented


@override_settings(WHATSAPP_WEBSITE_ORIGIN="https://clinic.example.test")
class ConsultationReplyConsentTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="+12025550123", password="Synthetic-Owner-Pass-123!",
        )
        self.other = get_user_model().objects.create_user(
            username="+12025550124", password="Synthetic-Other-Pass-123!",
        )
        self.staff = get_user_model().objects.create_user(
            username="synthetic-clinical-staff-consent", is_staff=True,
        )
        self.patient = Patient.objects.create(
            user=self.owner, full_name="Synthetic Consent Patient", phone_e164="+12025550123",
        )

    def _create(self, *, consent=False, language="ar"):
        return consultation_services.create_consultation(
            user=self.owner,
            question="Synthetic private question",
            uploaded_files=[],
            whatsapp_reply_notifications_consent=consent,
            consent_language=language,
        )

    def _reply(self, item, message="Synthetic private reply"):
        return consultation_services.update_consultation_reply(
            consultation=item, staff_user=self.staff, reply=message, status="answered",
        )

    def _guest(self, *, consent=False, verified=False, verified_late=False):
        evidence = (
            dict(whatsapp_reply_consent_at=timezone.now(),
                 whatsapp_reply_consent_version=VERSION,
                 whatsapp_reply_consent_language="ar")
            if consent else {}
        )
        guest = TransientConsultation.objects.create(
            phone_e164="+12025550125", question="Synthetic guest private question", **evidence,
        )
        if verified or verified_late:
            TransientConsultationChallenge.objects.create(
                consultation=guest,
                session_digest="synthetic-challenge",
                phone_e164=guest.phone_e164,
                otp_digest="synthetic-digest",
                verified_at=guest.created_at + (timedelta(seconds=1) if verified_late else -timedelta(seconds=1)),
                expires_at=timezone.now() + timedelta(minutes=10),
                grant_expires_at=timezone.now() + timedelta(minutes=10),
            )
        return guest

    def test_optional_consent_unchecked_ar_en_guest_and_registered(self):
        for form_type in (ConsultationCreateForm, GuestConsultationForm):
            for lang in ("ar", "en"):
                with self.subTest(form=form_type.__name__, language=lang):
                    form = form_type(language=lang)
                    field = form.fields["whatsapp_reply_notifications_consent"]
                    self.assertFalse(field.required)
                    self.assertFalse(field.initial)
                    self.assertFalse(form.is_bound)
                    self.assertIn("واتساب" if lang == "ar" else "WhatsApp", field.label)
                    self.assertTrue(form_type(
                        {"question": "Synthetic question"}, language=lang,
                    ).is_valid())
        self.assertNotIn(
            "whatsapp_reply_notifications_consent",
            GuestConsultationForm(
                language="ar", allow_whatsapp_notifications=False,
            ).fields,
        )

    def test_created_without_opt_in_legacy_unknown_and_unverified_guest_never_send(self):
        sender = Mock(return_value=True)
        existing = self._create()
        legacy = Consultation.objects.create(
            patient=self.patient, question="Synthetic legacy question",
        )
        unverified = self._guest(consent=True)
        late_verified = self._guest(consent=True, verified_late=True)
        self.assertIsNone(existing.whatsapp_reply_consent_at)
        self.assertEqual(legacy.whatsapp_reply_consent_version, "")
        self.assertFalse(unverified.phone_verified_at_submission)
        self.assertFalse(late_verified.phone_verified_at_submission)
        with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender):
            with self.captureOnCommitCallbacks(execute=True):
                for item in (existing, legacy, unverified, late_verified):
                    self._reply(item)
        sender.assert_not_called()

    def test_explicit_versioned_consent_sends_only_verified_destination(self):
        sender = Mock(return_value=True)
        registered = self._create(consent=True, language="en")
        verified_guest = self._guest(consent=True, verified=True)
        self.assertEqual(registered.whatsapp_reply_consent_version, VERSION)
        self.assertEqual(registered.whatsapp_reply_consent_language, "en")
        with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender):
            with self.captureOnCommitCallbacks(execute=True):
                self._reply(registered)
                self._reply(verified_guest)
        self.assertEqual(sender.call_count, 2)
        urls = [call.args[2] for call in sender.call_args_list]
        self.assertTrue(all(u.startswith("https://clinic.example.test/") for u in urls))
        self.assertNotIn("Synthetic private", repr(sender.call_args_list))

    def test_registered_owner_can_withdraw_with_post_and_wrong_user_cannot(self):
        c = self._create(consent=True)
        url = reverse(
            "patient_portal_consultation_whatsapp_withdraw",
            kwargs={"public_id": c.public_id},
        )
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        c.refresh_from_db()
        self.assertIsNotNone(c.whatsapp_reply_consent_withdrawn_at)
        first_withdrawal = c.whatsapp_reply_consent_withdrawn_at
        self.assertEqual(self.client.post(url).status_code, 302)
        c.refresh_from_db()
        self.assertEqual(c.whatsapp_reply_consent_withdrawn_at, first_withdrawal)
        with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=Mock(return_value=True)):
            self.assertFalse(send_reply_notification_if_consented(
                consultation_pk=c.pk,
            ))

    def test_dispatch_rechecks_withdrawal_and_version_even_if_queued(self):
        sender = Mock(return_value=True)
        c = self._create(consent=True)
        with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender):
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self._reply(c)
            self.assertTrue(callbacks)
            Consultation.objects.filter(pk=c.pk).update(
                whatsapp_reply_consent_withdrawn_at=timezone.now(),
            )
            for callback in callbacks:
                callback()
            self.assertFalse(send_reply_notification_if_consented(consultation_pk=c.pk))
        sender.assert_not_called()
        Consultation.objects.filter(pk=c.pk).update(
            whatsapp_reply_consent_withdrawn_at=None,
            whatsapp_reply_consent_version="legacy-unknown",
        )
        self.assertFalse(send_reply_notification_if_consented(consultation_pk=c.pk))

    def test_registered_form_opt_in_is_optional_in_post_flow(self):
        self.client.force_login(self.owner)
        for lang, route in (("ar", "patient_portal_consultation_new"), ("en", "patient_portal_consultation_new_en")):
            for accepted in (False, True):
                payload = {"question": "Synthetic form submission"}
                if accepted:
                    payload["whatsapp_reply_notifications_consent"] = "on"
                result = self.client.post(reverse(route), payload)
                self.assertEqual(result.status_code, 302)
                saved = Consultation.objects.filter(patient=self.patient).latest("pk")
                self.assertEqual(bool(saved.whatsapp_reply_consent_at), accepted)
                self.assertEqual(
                    saved.whatsapp_reply_consent_language,
                    lang if accepted else "",
                )

    def test_old_reply_remains_available_in_portal_after_opt_out(self):
        c = self._create(consent=True)
        with self.captureOnCommitCallbacks(execute=True):
            self._reply(c)
        self.client.force_login(self.owner)
        self.client.post(reverse(
            "patient_portal_consultation_whatsapp_withdraw",
            kwargs={"public_id": c.public_id},
        ))
        page = self.client.get(reverse(
            "patient_portal_consultation_detail",
            kwargs={"public_id": c.public_id},
        ))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Synthetic private reply")
