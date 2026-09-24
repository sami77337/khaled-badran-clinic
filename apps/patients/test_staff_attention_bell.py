from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.booking import services as booking_services
from apps.booking.models import Appointment, AppointmentStaffNotification
from apps.clinic.models import Doctor, DoctorSchedule, VisitType
from apps.patients import consultation_services
from apps.patients.context_processors import consultation_notifications
from apps.patients.models import (
    Consultation,
    ConsultationNotification,
    Patient,
    TransientConsultation,
)


class StaffAttentionBellTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.staff = users.objects.create_user(
            username="attention-staff",
            password="test-password",
            is_staff=True,
        )
        self.other_staff = users.objects.create_user(
            username="attention-other-staff",
            password="test-password",
            is_staff=True,
        )
        self.inactive_staff = users.objects.create_user(
            username="attention-inactive-staff",
            is_staff=True,
            is_active=False,
        )
        self.patient_user = users.objects.create_user(
            username="attention-patient",
            password="test-password",
        )
        self.patient = Patient.objects.create(
            user=self.patient_user,
            full_name="Synthetic Attention Patient",
            phone_raw="+962700000201",
            phone_e164="+962700000201",
        )
        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب تجريبي",
            full_name_en="Synthetic Doctor",
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="زيارة",
            name_en="Visit",
            duration_minutes=30,
        )
        self.factory = RequestFactory()

    def request_context(self, user=None, path="/dashboard/"):
        request = self.factory.get(path)
        request.user = user or self.staff
        return consultation_notifications(request)

    def appointment(self, offset):
        starts_at = timezone.now() + timedelta(days=2, minutes=offset)
        return Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            visit_type=self.visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
        )

    def test_owner_example_two_consultations_three_bookings_counts_five_then_two_then_zero(self):
        registered = Consultation.objects.create(
            patient=self.patient,
            question="Synthetic registered question",
        )
        guest = TransientConsultation.objects.create(
            phone_e164="+962700000202",
            display_name="Synthetic Guest",
            question="Synthetic guest question",
        )
        registered_notice = ConsultationNotification.objects.create(
            recipient=self.staff,
            consultation=registered,
            kind=ConsultationNotification.Kind.NEW_CONSULTATION,
        )
        for index in range(3):
            AppointmentStaffNotification.objects.create(
                recipient=self.staff,
                appointment=self.appointment(index * 60),
            )

        context = self.request_context()
        self.assertEqual(context["consultation_notification_unread_count"], 5)
        self.assertEqual(context["consultation_notification_consultation_count"], 2)
        self.assertEqual(context["consultation_notification_booking_unseen_count"], 3)

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("consultation_notifications_mark_all_read"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"bookings_seen": 3})
        self.assertFalse(
            AppointmentStaffNotification.objects.filter(
                recipient=self.staff,
                seen_at__isnull=True,
            ).exists()
        )
        registered_notice.refresh_from_db()
        self.assertIsNone(registered_notice.read_at)

        context = self.request_context()
        self.assertEqual(context["consultation_notification_unread_count"], 2)
        self.assertEqual(context["consultation_notification_consultation_count"], 2)

        with patch("apps.whatsapp.notifications.schedule_reply_notification"):
            consultation_services.update_consultation_reply(
                consultation=registered,
                staff_user=self.staff,
                reply="Synthetic staff reply",
                status=Consultation.Status.ANSWERED,
            )
        registered_notice.refresh_from_db()
        self.assertIsNotNone(registered_notice.read_at)
        self.assertEqual(
            self.request_context()["consultation_notification_unread_count"],
            1,
        )

        with patch("apps.whatsapp.notifications.schedule_reply_notification"):
            consultation_services.update_consultation_reply(
                consultation=guest,
                staff_user=self.staff,
                reply="Synthetic guest reply",
                status=Consultation.Status.ANSWERED,
            )
        context = self.request_context()
        self.assertEqual(context["consultation_notification_unread_count"], 0)
        self.assertEqual(context["consultation_notification_consultation_count"], 0)

    def test_opening_staff_consultation_does_not_resolve_attention(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            question="Synthetic attention stays pending",
        )
        notification = ConsultationNotification.objects.create(
            recipient=self.staff,
            consultation=consultation,
            kind=ConsultationNotification.Kind.NEW_CONSULTATION,
        )
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "consultation_notification_open",
                kwargs={"public_id": notification.public_id},
            )
        )
        self.assertEqual(response.status_code, 302)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)
        self.assertEqual(
            self.request_context()["consultation_notification_unread_count"],
            1,
        )

    def test_audio_reply_resolves_consultation_attention(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            question="Synthetic audio attention",
        )
        notification = ConsultationNotification.objects.create(
            recipient=self.staff,
            consultation=consultation,
            kind=ConsultationNotification.Kind.NEW_CONSULTATION,
        )
        audio = SimpleUploadedFile(
            "reply.webm",
            b"synthetic-audio",
            content_type="audio/webm",
        )

        with patch("apps.whatsapp.notifications.schedule_reply_notification"):
            consultation_services.update_consultation_reply(
                consultation=consultation,
                staff_user=self.staff,
                reply="",
                status=Consultation.Status.ANSWERED,
                audio_file=audio,
            )

        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertEqual(
            self.request_context()["consultation_notification_unread_count"],
            0,
        )

    def test_booking_seen_state_is_per_staff(self):
        appointment = self.appointment(0)
        own = AppointmentStaffNotification.objects.create(
            recipient=self.staff,
            appointment=appointment,
        )
        other = AppointmentStaffNotification.objects.create(
            recipient=self.other_staff,
            appointment=appointment,
        )
        self.client.force_login(self.staff)
        self.client.post(reverse("consultation_notifications_mark_all_read"))

        own.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNotNone(own.seen_at)
        self.assertIsNone(other.seen_at)

    def test_patient_reply_notification_still_becomes_read_when_opened(self):
        consultation = Consultation.objects.create(
            patient=self.patient,
            question="Synthetic patient-side notification",
            staff_reply="Synthetic existing answer",
            replied_at=timezone.now(),
            replied_by=self.staff,
            status=Consultation.Status.ANSWERED,
        )
        notification = ConsultationNotification.objects.create(
            recipient=self.patient_user,
            consultation=consultation,
            kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
        )
        self.client.force_login(self.patient_user)

        response = self.client.post(
            reverse(
                "consultation_notification_open",
                kwargs={"public_id": notification.public_id},
            )
        )
        self.assertEqual(response.status_code, 302)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

    def test_public_booking_creates_seen_state_for_active_staff_only(self):
        target_day = timezone.localdate() + timedelta(days=2)
        starts_at = timezone.make_aware(
            datetime.combine(target_day, time(10, 0)),
            timezone.get_current_timezone(),
        )
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            weekday=target_day.weekday(),
            start_time=time(9, 0),
            end_time=time(13, 0),
        )

        with patch("apps.whatsapp.booking.schedule_booking_confirmation"), patch(
            "apps.notifications.services.schedule_staff_event"
        ):
            appointment = booking_services.create_public_appointment(
                full_name="Synthetic Booking Patient",
                phone_raw="+962700000299",
                visit_type_id=self.visit_type.pk,
                starts_at=starts_at,
            )

        recipients = set(
            AppointmentStaffNotification.objects.filter(
                appointment=appointment,
            ).values_list("recipient_id", flat=True)
        )
        self.assertEqual(recipients, {self.staff.pk, self.other_staff.pk})
        self.assertNotIn(self.inactive_staff.pk, recipients)

    def test_bell_open_javascript_marks_only_bookings_seen(self):
        source = (
            Path(settings.BASE_DIR) / "static" / "js" / "consultation-notifications.js"
        ).read_text(encoding="utf-8")

        self.assertIn('root.dataset.staffAttentionBell === "true"', source)
        self.assertIn("syncSeenBookings(root)", source)
        self.assertIn('"X-Requested-With": "XMLHttpRequest"', source)
        self.assertNotIn("ConsultationNotification", source)
