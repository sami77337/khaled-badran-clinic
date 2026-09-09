from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import resolve, reverse

from apps.patients.consultation_services import update_consultation_reply
from apps.patients.models import Consultation, Patient, TransientConsultation
from apps.whatsapp.actions import entry_actions
from apps.whatsapp.notifications import REPLY_MESSAGES


@override_settings(WHATSAPP_WEBSITE_ORIGIN="https://clinic.example.test")
class ConsultationWhatsAppTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username="synthetic-notification-staff", is_staff=True)
        cls.owner = get_user_model().objects.create_user(username="synthetic-notification-owner")
        cls.patient = Patient.objects.create(user=cls.owner, full_name="Synthetic", phone_e164="+12025550101")
        cls.registered = Consultation.objects.create(patient=cls.patient, question="Synthetic sensitive question")
        cls.guest = TransientConsultation.objects.create(phone_e164="+12025550102", question="Synthetic sensitive guest question", language="en")

    def reply(self, consultation, text="Synthetic sensitive reply"):
        return update_consultation_reply(consultation=consultation, staff_user=self.staff, reply=text, status="answered")

    def test_localized_menu_destinations_resolve_to_existing_routes(self):
        for language, prefix in (("ar", ""), ("en", "/en")):
            actions = {item.key: item for item in entry_actions(language)}
            self.assertEqual(actions["book"].url, prefix + "/book/")
            self.assertEqual(actions["consult_patient"].url, prefix + "/portal/consultations/new/")
            self.assertEqual(actions["consult_guest"].url, prefix + "/consult/")
            self.assertEqual(actions["location"].url, prefix + "/contact-location/")
            for action in actions.values():
                self.assertTrue(resolve(action.url))

    def test_notifications_have_only_neutral_text_and_protected_links(self):
        sender = Mock(return_value=True)
        for guest in (False, True):
            for language in ("ar", "en"):
                item = self.guest if guest else self.registered
                if guest:
                    item.language = language
                    item.save(update_fields=["language"])
                with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender, WHATSAPP_DEFAULT_LANGUAGE=language):
                    with self.captureOnCommitCallbacks(execute=True):
                        self.reply(item, text="Synthetic sensitive reply " + language)
                phone, message, url, sent_language = sender.call_args.args
                self.assertEqual(message, REPLY_MESSAGES[language])
                self.assertEqual(sent_language, language)
                self.assertNotIn("Synthetic", message + url)
                self.assertNotIn(phone, message + url)
                route = "guest_consultation_detail" if guest else "patient_portal_consultation_detail"
                self.assertEqual(url, "https://clinic.example.test" + reverse(route + ("_en" if language == "en" else ""), kwargs={"public_id": item.public_id}))
                self.assertEqual(len(sender.call_args.args), 4)
                self.assertFalse(sender.call_args.kwargs)

    def test_sender_failures_do_not_rollback_saved_replies_and_logs_are_safe(self):
        for item in (self.registered, self.guest):
            for index, sender in enumerate(("", "invalid.module.sender", Mock(return_value=False), Mock(side_effect=RuntimeError("Synthetic sensitive reply +12025550102 secret-token")))):
                with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender):
                    with self.assertLogs("apps.whatsapp.notifications", level="WARNING") as logs:
                        with self.captureOnCommitCallbacks(execute=True):
                            self.reply(item, "Synthetic sensitive reply " + str(index))
                item.refresh_from_db()
                self.assertEqual(item.staff_reply, "Synthetic sensitive reply " + str(index))
                self.assertIsNotNone(item.replied_at)
                for secret in ("Synthetic", "+12025550102", "secret-token"):
                    self.assertNotIn(secret, "".join(logs.output))

    def test_sending_waits_for_commit_and_rollback_sends_nothing(self):
        sender = Mock(return_value=True)
        with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        self.reply(self.guest)
                        self.assertFalse(sender.called)
                        raise RuntimeError("Synthetic rollback")
            self.assertFalse(sender.called)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.staff_reply, "")

    def test_unchanged_reply_and_status_only_do_not_send_again(self):
        sender = Mock(return_value=True)
        with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender):
            with self.captureOnCommitCallbacks(execute=True):
                self.reply(self.guest)
                self.reply(self.guest)
                update_consultation_reply(consultation=self.guest, staff_user=self.staff, reply="Synthetic sensitive reply", status="closed")
        self.assertEqual(sender.call_count, 1)

    def test_untrusted_or_missing_origin_never_sends(self):
        sender = Mock(return_value=True)
        for origin in ("", "http://clinic.example.test", "https://user:secret@clinic.example.test", "https://clinic.example.test/path", "https://clinic.example.test?redirect=evil"):
            with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=sender, WHATSAPP_WEBSITE_ORIGIN=origin):
                with self.captureOnCommitCallbacks(execute=True):
                    self.reply(self.guest, "Synthetic " + origin)
        self.assertFalse(sender.called)


@override_settings(WHATSAPP_WEBSITE_ORIGIN="https://clinic.example.test")
class ConsultationNotificationCommitTests(TransactionTestCase):
    def test_provider_exception_after_real_commit_preserves_both_reply_types(self):
        staff = get_user_model().objects.create_user(username="synthetic-commit-staff", is_staff=True)
        patient = Patient.objects.create(full_name="Synthetic", phone_e164="+12025550101")
        items = [Consultation.objects.create(patient=patient, question="Synthetic question"),
                 TransientConsultation.objects.create(phone_e164="+12025550102", question="Synthetic question")]
        for item in items:
            committed = []
            def fail_after_commit(*args):
                committed.append(transaction.get_autocommit() and type(item).objects.get(pk=item.pk).staff_reply == "Synthetic reply")
                raise RuntimeError("Synthetic secret from provider")
            with self.settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=fail_after_commit):
                with self.assertLogs("apps.whatsapp.notifications", level="WARNING") as logs:
                    update_consultation_reply(consultation=item, staff_user=staff, reply="Synthetic reply", status="answered")
            self.assertEqual(committed, [True])
            item.refresh_from_db()
            self.assertEqual(item.staff_reply, "Synthetic reply")
            self.assertNotIn("Synthetic secret", "".join(logs.output))
