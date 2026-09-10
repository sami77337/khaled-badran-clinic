from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.patients import consultation_services
from apps.patients.models import (
    Consultation,
    ConsultationAudioReply,
    ConsultationNotification,
    Patient,
)


class ConsultationNotificationEventTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._private_media_directory = TemporaryDirectory()
        cls._private_media_override = override_settings(
            PRIVATE_MEDIA_ROOT=cls._private_media_directory.name
        )
        cls._private_media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._private_media_override.disable()
        cls._private_media_directory.cleanup()

    def setUp(self):
        user_model = get_user_model()
        self.patient_user = user_model.objects.create_user(username="notification-patient")
        self.staff = user_model.objects.create_user(
            username="notification-staff",
            is_staff=True,
        )
        self.second_staff = user_model.objects.create_user(
            username="notification-second-staff",
            is_staff=True,
        )
        self.inactive_staff = user_model.objects.create_user(
            username="notification-inactive-staff",
            is_staff=True,
            is_active=False,
        )
        self.unrelated_patient_user = user_model.objects.create_user(
            username="notification-unrelated-patient"
        )
        self.patient = Patient.objects.create(
            user=self.patient_user,
            full_name="Synthetic Notification Patient",
            phone_raw="+962700000101",
            phone_e164="+962700000101",
        )

    def create_consultation(self, question="Synthetic private consultation question"):
        return Consultation.objects.create(patient=self.patient, question=question)

    def audio_upload(self, name="reply.webm", content=b"synthetic-audio"):
        return SimpleUploadedFile(name, content, content_type="audio/webm")

    def test_creation_notifies_each_active_staff_recipient_and_no_patient(self):
        consultation = consultation_services.create_consultation(
            user=self.patient_user,
            question="Synthetic consultation",
            uploaded_files=[],
        )

        notifications = ConsultationNotification.objects.filter(
            consultation=consultation,
            kind=ConsultationNotification.Kind.NEW_CONSULTATION,
        )
        self.assertEqual(notifications.count(), 2)
        self.assertSetEqual(
            set(notifications.values_list("recipient_id", flat=True)),
            {self.staff.pk, self.second_staff.pk},
        )
        self.assertFalse(notifications.exclude(read_at__isnull=True).exists())
        self.assertFalse(
            ConsultationNotification.objects.filter(recipient=self.patient_user).exists()
        )
        self.assertFalse(notifications.filter(recipient=self.inactive_staff).exists())
        self.assertFalse(notifications.filter(recipient=self.unrelated_patient_user).exists())

    def test_creation_succeeds_without_staff_and_failure_rolls_back_notifications(self):
        get_user_model().objects.filter(is_staff=True).update(is_active=False)
        consultation = consultation_services.create_consultation(
            user=self.patient_user,
            question="No staff available",
            uploaded_files=[],
        )
        self.assertTrue(Consultation.objects.filter(pk=consultation.pk).exists())
        self.assertFalse(ConsultationNotification.objects.exists())

        self.staff.is_active = True
        self.staff.save(update_fields=["is_active"])
        with patch.object(
            ConsultationNotification.objects,
            "bulk_create",
            side_effect=RuntimeError("synthetic notification failure"),
        ), self.assertRaises(RuntimeError):
            consultation_services.create_consultation(
                user=self.patient_user,
                question="Rolled back consultation",
                uploaded_files=[],
            )
        self.assertFalse(
            Consultation.objects.filter(question="Rolled back consultation").exists()
        )

    def test_first_text_reply_notifies_only_owning_patient(self):
        consultation = self.create_consultation()
        consultation_services.update_consultation_reply(
            consultation=consultation,
            staff_user=self.staff,
            reply="Synthetic written reply",
            status=Consultation.Status.ANSWERED,
        )

        notification = ConsultationNotification.objects.get(
            consultation=consultation,
            kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
        )
        self.assertEqual(notification.recipient, self.patient_user)
        self.assertIsNone(notification.read_at)

    def test_audio_only_and_combined_replies_each_create_one_notification(self):
        audio_only = self.create_consultation("Audio-only notification")
        combined = self.create_consultation("Combined notification")

        consultation_services.update_consultation_reply(
            consultation=audio_only,
            staff_user=self.staff,
            reply="",
            status=Consultation.Status.ANSWERED,
            audio_file=self.audio_upload(),
        )
        consultation_services.update_consultation_reply(
            consultation=combined,
            staff_user=self.staff,
            reply="Synthetic combined reply",
            status=Consultation.Status.ANSWERED,
            audio_file=self.audio_upload(name="combined.webm", content=b"combined-audio"),
        )

        for consultation in (audio_only, combined):
            with self.subTest(consultation=consultation.pk):
                self.assertEqual(
                    ConsultationNotification.objects.filter(
                        consultation=consultation,
                        recipient=self.patient_user,
                        kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
                    ).count(),
                    1,
                )
        self.assertEqual(audio_only.staff_reply, "")
        self.assertTrue(ConsultationAudioReply.objects.filter(consultation=audio_only).exists())

    def test_status_only_change_does_not_notify_and_reply_failure_rolls_back(self):
        status_only = self.create_consultation("Status only")
        consultation_services.update_consultation_reply(
            consultation=status_only,
            staff_user=self.staff,
            reply="",
            status=Consultation.Status.CLOSED,
        )
        self.assertFalse(
            ConsultationNotification.objects.filter(
                consultation=status_only,
                kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
            ).exists()
        )

        failed = self.create_consultation("Failed reply")
        with patch.object(
            ConsultationNotification.objects,
            "get_or_create",
            side_effect=RuntimeError("synthetic reply notification failure"),
        ), self.assertRaises(RuntimeError):
            consultation_services.update_consultation_reply(
                consultation=failed,
                staff_user=self.staff,
                reply="Must roll back",
                status=Consultation.Status.ANSWERED,
            )
        failed.refresh_from_db()
        self.assertEqual(failed.staff_reply, "")
        self.assertEqual(failed.status, Consultation.Status.NEW)
        self.assertIsNone(failed.staff_handled_at)
        self.assertFalse(ConsultationNotification.objects.filter(consultation=failed).exists())

    def test_audio_reply_notification_failure_rolls_back_audio_and_reply_state(self):
        consultation = self.create_consultation("Failed audio reply")
        with patch.object(
            ConsultationNotification.objects,
            "get_or_create",
            side_effect=RuntimeError("synthetic reply notification failure"),
        ), self.assertRaises(RuntimeError):
            consultation_services.update_consultation_reply(
                consultation=consultation,
                staff_user=self.staff,
                reply="",
                status=Consultation.Status.ANSWERED,
                audio_file=self.audio_upload(),
            )
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.NEW)
        self.assertIsNone(consultation.staff_handled_at)
        self.assertFalse(ConsultationAudioReply.objects.filter(consultation=consultation).exists())
        self.assertFalse(ConsultationNotification.objects.filter(consultation=consultation).exists())

    def test_later_edits_audio_replacement_and_removal_do_not_duplicate(self):
        consultation = self.create_consultation()
        consultation_services.update_consultation_reply(
            consultation=consultation,
            staff_user=self.staff,
            reply="First visible reply",
            status=Consultation.Status.ANSWERED,
        )
        consultation_services.update_consultation_reply(
            consultation=consultation,
            staff_user=self.second_staff,
            reply="Edited visible reply",
            status=Consultation.Status.ANSWERED,
            audio_file=self.audio_upload(),
        )
        consultation_services.update_consultation_reply(
            consultation=consultation,
            staff_user=self.second_staff,
            reply="",
            status=Consultation.Status.CLOSED,
            remove_audio=True,
        )
        consultation_services.update_consultation_reply(
            consultation=consultation,
            staff_user=self.second_staff,
            reply="",
            status=Consultation.Status.ANSWERED,
            audio_file=self.audio_upload(name="recorded-again.webm", content=b"new-audio"),
        )

        self.assertEqual(
            ConsultationNotification.objects.filter(
                consultation=consultation,
                kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
            ).count(),
            1,
        )

    def test_unique_contract_and_model_do_not_store_notification_copy(self):
        consultation = self.create_consultation()
        ConsultationNotification.objects.create(
            recipient=self.patient_user,
            consultation=consultation,
            kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConsultationNotification.objects.create(
                recipient=self.patient_user,
                consultation=consultation,
                kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
            )
        field_names = {field.name for field in ConsultationNotification._meta.fields}
        self.assertTrue({"public_id", "recipient", "consultation", "kind", "read_at", "created_at"} <= field_names)
        self.assertTrue({"message", "body", "title"}.isdisjoint(field_names))

    def test_inactive_patient_is_notified_and_missing_recipient_is_skipped_safely(self):
        self.patient_user.is_active = False
        self.patient_user.save(update_fields=["is_active"])
        inactive_consultation = self.create_consultation("Inactive owner")
        consultation_services.update_consultation_reply(
            consultation=inactive_consultation,
            staff_user=self.staff,
            reply="Visible reply",
            status=Consultation.Status.ANSWERED,
        )

        missing_patient = Patient.objects.create(
            full_name="Patient without account",
            phone_raw="+962700000102",
        )
        missing_consultation = Consultation.objects.create(
            patient=missing_patient,
            question="Missing owner",
        )
        consultation_services.update_consultation_reply(
            consultation=missing_consultation,
            staff_user=self.staff,
            reply="Visible reply",
            status=Consultation.Status.ANSWERED,
        )
        self.assertTrue(
            ConsultationNotification.objects.filter(
                recipient=self.patient_user,
                consultation=inactive_consultation,
                kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
            ).exists()
        )
        self.assertFalse(
            ConsultationNotification.objects.filter(
                consultation=missing_consultation,
                kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
            ).exists()
        )


class ConsultationNotificationReadAndPrivacyTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.patient_a_user = user_model.objects.create_user(username="notification-owner-a")
        self.patient_b_user = user_model.objects.create_user(username="notification-owner-b")
        self.staff = user_model.objects.create_user(username="notification-doctor", is_staff=True)
        self.other_staff = user_model.objects.create_user(
            username="notification-other-doctor",
            is_staff=True,
        )
        self.patient_a = Patient.objects.create(
            user=self.patient_a_user,
            full_name="PRIVATE PATIENT A NAME",
            phone_raw="PRIVATE-PHONE-A",
        )
        self.patient_b = Patient.objects.create(
            user=self.patient_b_user,
            full_name="PRIVATE PATIENT B NAME",
            phone_raw="PRIVATE-PHONE-B",
        )
        self.consultation_a = Consultation.objects.create(
            patient=self.patient_a,
            question="PRIVATE QUESTION A MUST NOT LEAK",
        )
        self.consultation_b = Consultation.objects.create(
            patient=self.patient_b,
            question="PRIVATE QUESTION B MUST NOT LEAK",
        )
        self.patient_notification = ConsultationNotification.objects.create(
            recipient=self.patient_a_user,
            consultation=self.consultation_a,
            kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
        )
        self.other_patient_notification = ConsultationNotification.objects.create(
            recipient=self.patient_b_user,
            consultation=self.consultation_b,
            kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
        )
        self.staff_notification = ConsultationNotification.objects.create(
            recipient=self.staff,
            consultation=self.consultation_a,
            kind=ConsultationNotification.Kind.NEW_CONSULTATION,
        )

    def open_url(self, notification, english=False):
        return reverse(
            "consultation_notification_open_en" if english else "consultation_notification_open",
            kwargs={"public_id": notification.public_id},
        )

    def test_owner_post_open_marks_read_redirects_and_is_idempotent(self):
        self.client.force_login(self.patient_a_user)
        response = self.client.post(self.open_url(self.patient_notification, english=True))
        self.assertRedirects(
            response,
            reverse(
                "patient_portal_consultation_detail_en",
                kwargs={"public_id": self.consultation_a.public_id},
            ),
            fetch_redirect_response=False,
        )
        self.patient_notification.refresh_from_db()
        first_read_at = self.patient_notification.read_at
        self.assertIsNotNone(first_read_at)

        repeated = self.client.post(self.open_url(self.patient_notification, english=True))
        self.assertEqual(repeated.status_code, 302)
        self.patient_notification.refresh_from_db()
        self.assertEqual(self.patient_notification.read_at, first_read_at)

    def test_staff_post_open_marks_read_and_redirects_to_private_dashboard(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.open_url(self.staff_notification, english=True))
        expected = reverse(
            "dashboard_consultation_detail",
            kwargs={"public_id": self.consultation_a.public_id},
        )
        self.assertRedirects(response, f"{expected}?lang=en", fetch_redirect_response=False)
        self.staff_notification.refresh_from_db()
        self.assertIsNotNone(self.staff_notification.read_at)

    def test_get_does_not_mutate_and_anonymous_is_denied(self):
        self.client.force_login(self.patient_a_user)
        get_response = self.client.get(self.open_url(self.patient_notification))
        self.assertEqual(get_response.status_code, 405)
        self.patient_notification.refresh_from_db()
        self.assertIsNone(self.patient_notification.read_at)

        self.client.logout()
        anonymous = self.client.post(self.open_url(self.patient_notification))
        self.assertEqual(anonymous.status_code, 302)
        self.patient_notification.refresh_from_db()
        self.assertIsNone(self.patient_notification.read_at)

    def test_cross_user_and_cross_role_post_open_are_denied(self):
        cases = (
            (self.patient_a_user, self.other_patient_notification),
            (self.patient_a_user, self.staff_notification),
            (self.other_staff, self.patient_notification),
        )
        for user, notification in cases:
            with self.subTest(user=user.username, notification=notification.kind):
                self.client.force_login(user)
                response = self.client.post(self.open_url(notification))
                self.assertEqual(response.status_code, 404)
                notification.refresh_from_db()
                self.assertIsNone(notification.read_at)

    def test_mark_all_updates_only_current_user_and_get_does_not_write(self):
        second_consultation = Consultation.objects.create(
            patient=self.patient_a,
            question="Second synthetic question",
        )
        second = ConsultationNotification.objects.create(
            recipient=self.patient_a_user,
            consultation=second_consultation,
            kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
        )
        mark_all_url = reverse("consultation_notifications_mark_all_read_en")
        self.client.force_login(self.patient_a_user)
        self.assertEqual(self.client.get(mark_all_url).status_code, 405)
        response = self.client.post(mark_all_url, {"next": "https://invalid.example/"})
        self.assertRedirects(
            response,
            reverse("patient_portal_consultation_list_en"),
            fetch_redirect_response=False,
        )
        self.patient_notification.refresh_from_db()
        second.refresh_from_db()
        self.other_patient_notification.refresh_from_db()
        self.assertIsNotNone(self.patient_notification.read_at)
        self.assertIsNotNone(second.read_at)
        self.assertIsNone(self.other_patient_notification.read_at)

    def test_read_actions_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.patient_a_user)
        self.assertEqual(
            csrf_client.post(self.open_url(self.patient_notification)).status_code,
            403,
        )
        self.assertEqual(
            csrf_client.post(reverse("consultation_notifications_mark_all_read")).status_code,
            403,
        )

    def test_public_header_is_anonymous_safe_and_localized_for_patient_and_staff(self):
        for route in ("home", "home_en"):
            with self.subTest(route=route, user="anonymous"):
                response = self.client.get(reverse(route))
                self.assertNotContains(response, "data-consultation-notifications")
                self.assertNotContains(response, "consultation-notification-panel")

        self.client.force_login(self.patient_a_user)
        patient_ar = self.client.get(reverse("home"))
        patient_en = self.client.get(reverse("home_en"))
        self.assertContains(patient_ar, "تم الرد على استشارتك", count=2)
        self.assertContains(patient_en, "Your consultation has been answered", count=2)
        self.assertContains(patient_en, 'method="post"')
        self.assertNotContains(patient_en, self.consultation_a.question)
        self.assertNotContains(patient_en, self.patient_a.full_name)
        self.assertNotContains(patient_en, self.patient_a.phone_raw)

        self.client.force_login(self.staff)
        staff_ar = self.client.get(reverse("home"))
        staff_en = self.client.get(reverse("home_en"))
        self.assertContains(staff_ar, "استشارة جديدة", count=2)
        self.assertContains(staff_en, "New consultation", count=2)
        self.assertNotContains(staff_en, self.consultation_a.question)
        self.assertNotContains(staff_en, self.patient_a.full_name)
        self.assertNotContains(staff_en, self.patient_a.phone_raw)

    def test_dropdown_limits_results_and_badge_caps_above_99(self):
        consultations = [
            Consultation(patient=self.patient_a, question=f"Synthetic question {index}")
            for index in range(100)
        ]
        Consultation.objects.bulk_create(consultations)
        ConsultationNotification.objects.bulk_create(
            [
                ConsultationNotification(
                    recipient=self.patient_a_user,
                    consultation=consultation,
                    kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
                )
                for consultation in consultations
            ]
        )
        self.client.force_login(self.patient_a_user)
        response = self.client.get(reverse("home_en"))
        self.assertContains(response, "99+")
        self.assertEqual(response.context["consultation_notification_unread_count"], 101)
        self.assertEqual(len(response.context["consultation_notification_items"]), 10)
