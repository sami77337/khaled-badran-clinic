from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.booking import operations
from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.patients.models import Patient


class AppointmentOperationsCloseoutTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="appointment-closeout-staff",
            password="test-password",
            is_staff=True,
        )
        self.doctor = Doctor.objects.create(
            full_name_ar="خالد حسان بدران",
            full_name_en="Khaled Hassan Badran",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="استشاري الأنف والأذن والحنجرة",
            specialty_en="ENT consultant",
            is_active=True,
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="كشف جديد",
            name_en="New consultation",
            duration_minutes=30,
            is_active=True,
        )
        self.patient = Patient.objects.create(
            full_name="Closeout Patient",
            phone_raw="0791234567",
            phone_e164="+962791234567",
        )
        self.now = timezone.now().replace(microsecond=0)

    def appointment(self, minutes, *, status=Appointment.Status.CONFIRMED, patient=None):
        starts_at = self.now + timedelta(minutes=minutes)
        return Appointment.objects.create(
            doctor=self.doctor,
            patient=patient or self.patient,
            visit_type=self.visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=status,
        )

    def test_needs_classification_is_derived_and_does_not_mutate_status(self):
        past_confirmed = self.appointment(-120)
        past_rescheduled = self.appointment(-90, status=Appointment.Status.RESCHEDULED)
        future_confirmed = self.appointment(60)
        past_arrived = self.appointment(-60, status=Appointment.Status.ARRIVED)

        ids = set(
            operations.needs_classification_queryset(now=self.now).values_list("id", flat=True)
        )

        self.assertEqual(ids, {past_confirmed.id, past_rescheduled.id})
        future_confirmed.refresh_from_db()
        past_arrived.refresh_from_db()
        self.assertEqual(future_confirmed.status, Appointment.Status.CONFIRMED)
        self.assertEqual(past_arrived.status, Appointment.Status.ARRIVED)

    def test_no_show_is_blocked_before_start_time(self):
        appointment = self.appointment(60)

        with self.assertRaises(ValidationError):
            operations.mark_no_show(
                appointment.id,
                actor=self.staff,
                note="Patient did not arrive.",
                now=self.now,
            )

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

    def test_no_show_is_allowed_after_start_time(self):
        appointment = self.appointment(-60)

        operations.mark_no_show(
            appointment.id,
            actor=self.staff,
            note="Patient did not arrive.",
            now=self.now,
        )

        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.NO_SHOW)

    def test_follow_up_queue_requires_staff_and_shows_only_derived_queue(self):
        queued = self.appointment(-120)
        completed_patient = Patient.objects.create(
            full_name="Completed Patient",
            phone_raw="0791111111",
            phone_e164="+962791111111",
        )
        completed = self.appointment(
            -60,
            status=Appointment.Status.COMPLETED,
            patient=completed_patient,
        )
        future_patient = Patient.objects.create(
            full_name="Future Patient",
            phone_raw="0792222222",
            phone_e164="+962792222222",
        )
        future = self.appointment(60, patient=future_patient)
        url = reverse("dashboard_appointment_follow_up")

        anonymous = self.client.get(url)
        self.assertEqual(anonymous.status_code, 302)

        self.client.force_login(self.staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, queued.patient.full_name)
        self.assertNotContains(response, completed.patient.full_name)
        self.assertNotContains(response, future.patient.full_name)
        self.assertContains(response, "بحاجة إلى تصنيف")

    def test_follow_up_arrived_quick_action_moves_item_to_arrived(self):
        appointment = self.appointment(-90)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "dashboard_appointment_follow_up_arrived",
                kwargs={"appointment_id": appointment.id},
            )
        )

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.ARRIVED)

    def test_follow_up_no_show_requires_internal_reason(self):
        appointment = self.appointment(-90)
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_follow_up_no_show",
            kwargs={"appointment_id": appointment.id},
        )

        response = self.client.post(url, {"note": ""})
        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

        response = self.client.post(url, {"note": "Patient did not arrive."})
        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.NO_SHOW)

    def test_follow_up_complete_quick_action_only_completes_arrived(self):
        arrived = self.appointment(-90, status=Appointment.Status.ARRIVED)
        confirmed = self.appointment(-60)
        self.client.force_login(self.staff)

        arrived_response = self.client.post(
            reverse(
                "dashboard_appointment_follow_up_complete",
                kwargs={"appointment_id": arrived.id},
            )
        )
        self.assertEqual(arrived_response.status_code, 302)
        arrived.refresh_from_db()
        self.assertEqual(arrived.status, Appointment.Status.COMPLETED)

        confirmed_response = self.client.post(
            reverse(
                "dashboard_appointment_follow_up_complete",
                kwargs={"appointment_id": confirmed.id},
            )
        )
        self.assertEqual(confirmed_response.status_code, 302)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, Appointment.Status.CONFIRMED)

    def test_dashboard_shows_low_noise_follow_up_count_in_both_languages(self):
        self.appointment(-90)
        self.appointment(60)
        self.client.force_login(self.staff)

        arabic = self.client.get(reverse("dashboard_home"))
        english = self.client.get(f"{reverse('dashboard_home')}?lang=en")

        self.assertEqual(arabic.status_code, 200)
        self.assertEqual(english.status_code, 200)
        self.assertContains(arabic, "تحتاج متابعة (1)")
        self.assertContains(english, "Needs Follow-up (1)")
