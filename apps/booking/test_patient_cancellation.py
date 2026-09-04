from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.booking import operations, services
from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog, SystemSetting
from apps.patients import views as patient_views
from apps.patients.models import Patient


class PatientAppointmentCancellationTests(TestCase):
    password = "Patient-cancel-pass-382!"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="+962795000001",
            password=self.password,
        )
        self.other = get_user_model().objects.create_user(
            username="+962795000002",
            password=self.password,
        )
        self.staff = get_user_model().objects.create_user(
            username="cancellation-staff",
            password=self.password,
            is_staff=True,
        )
        self.patient = Patient.objects.create(
            user=self.user,
            full_name="Cancellation Patient",
            phone_raw=self.user.username,
            phone_e164=self.user.username,
        )
        self.other_patient = Patient.objects.create(
            user=self.other,
            full_name="Other Cancellation Patient",
            phone_raw=self.other.username,
            phone_e164=self.other.username,
        )
        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب الإلغاء",
            full_name_en="Cancellation Doctor",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="اختبار",
            specialty_en="Test",
            is_active=True,
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="زيارة إلغاء",
            name_en="Cancellation Visit",
            duration_minutes=30,
            is_active=True,
        )
        self._minute_offset = 0

    def create_appointment(
        self,
        *,
        patient=None,
        status=Appointment.Status.CONFIRMED,
        starts_at=None,
    ):
        self._minute_offset += 1
        starts_at = starts_at or (
            timezone.now() + timedelta(days=2, minutes=self._minute_offset)
        )
        return Appointment.objects.create(
            doctor=self.doctor,
            patient=patient or self.patient,
            visit_type=self.visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=status,
        )

    def cancellation_url(self, appointment, *, english=False):
        return reverse(
            "patient_portal_appointment_cancel_en"
            if english
            else "patient_portal_appointment_cancel",
            kwargs={
                "reference": patient_views._appointment_cancellation_reference(appointment)
            },
        )

    def test_default_and_exact_cutoff_eligibility(self):
        self.assertEqual(
            services.get_booking_settings().patient_cancellation_cutoff_minutes,
            720,
        )
        now = timezone.now()
        over = self.create_appointment(starts_at=now + timedelta(hours=13))
        exact = self.create_appointment(starts_at=now + timedelta(hours=12))
        under = self.create_appointment(starts_at=now + timedelta(hours=12) - timedelta(seconds=1))
        self.assertTrue(operations.patient_can_cancel_appointment(over, self.user, now=now))
        self.assertTrue(operations.patient_can_cancel_appointment(exact, self.user, now=now))
        self.assertFalse(operations.patient_can_cancel_appointment(under, self.user, now=now))

    def test_custom_cutoff_and_ownership_apply_server_side(self):
        SystemSetting.objects.create(
            key=SystemSetting.PATIENT_CANCELLATION_CUTOFF_MINUTES,
            value="1440",
            value_type=SystemSetting.ValueType.DURATION_MINUTES,
        )
        appointment = self.create_appointment(starts_at=timezone.now() + timedelta(hours=13))
        other_appointment = self.create_appointment(patient=self.other_patient)
        self.assertFalse(operations.patient_can_cancel_appointment(appointment, self.user))
        self.assertFalse(operations.patient_can_cancel_appointment(other_appointment, self.user))
        with self.assertRaises(ValidationError):
            operations.patient_cancel_appointment(
                public_token=other_appointment.public_token,
                user=self.user,
            )

    def test_confirmed_and_rescheduled_allowed_other_states_denied(self):
        for status in (Appointment.Status.CONFIRMED, Appointment.Status.RESCHEDULED):
            with self.subTest(status=status):
                appointment = self.create_appointment(status=status)
                self.assertTrue(operations.patient_can_cancel_appointment(appointment, self.user))

        for status in (
            Appointment.Status.ARRIVED,
            Appointment.Status.COMPLETED,
            Appointment.Status.CANCELLED,
            Appointment.Status.NO_SHOW,
        ):
            with self.subTest(status=status):
                appointment = self.create_appointment(status=status)
                self.assertFalse(operations.patient_can_cancel_appointment(appointment, self.user))
                with self.assertRaises(ValidationError):
                    operations.patient_cancel_appointment(
                        public_token=appointment.public_token,
                        user=self.user,
                    )

    def test_cancellation_preserves_row_and_creates_history_audit_and_frees_slot(self):
        appointment = self.create_appointment()
        appointment_id = appointment.pk
        result = operations.patient_cancel_appointment(
            public_token=appointment.public_token,
            user=self.user,
        )
        self.assertEqual(result.status, Appointment.Status.CANCELLED)
        self.assertTrue(Appointment.objects.filter(pk=appointment_id).exists())
        history = AppointmentStatusHistory.objects.get(appointment=appointment)
        self.assertEqual(history.old_status, Appointment.Status.CONFIRMED)
        self.assertEqual(history.new_status, Appointment.Status.CANCELLED)
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(history.note, operations.PATIENT_CANCELLATION_NOTE)
        audit = AuditLog.objects.get(
            app_label="booking",
            model_name="Appointment",
            object_id=str(appointment_id),
        )
        self.assertEqual(audit.action, AuditLog.Action.STATUS_CHANGE)
        self.assertEqual(audit.message, operations.PATIENT_CANCELLATION_NOTE)
        self.assertFalse(
            services.overlaps_existing_appointment(
                self.doctor,
                appointment.starts_at,
                appointment.ends_at,
            )
        )

    def test_confirmation_ui_revalidates_changed_state_at_post(self):
        appointment = self.create_appointment()
        self.client.force_login(self.user)
        detail = self.client.get(
            reverse(
                "patient_portal_appointment_detail_en",
                kwargs={"public_token": appointment.public_token},
            )
        )
        self.assertContains(detail, "Cancel Appointment")
        self.assertNotContains(detail, str(appointment.public_token))
        confirmation = self.client.get(self.cancellation_url(appointment, english=True))
        self.assertContains(confirmation, "12 hours")

        appointment.status = Appointment.Status.ARRIVED
        appointment.save(update_fields=["status", "updated_at"])
        response = self.client.post(self.cancellation_url(appointment, english=True), follow=True)
        self.assertContains(response, "could not be cancelled")
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.ARRIVED)

    def test_successful_patient_view_cancel_and_access_controls(self):
        appointment = self.create_appointment()
        self.client.force_login(self.user)
        response = self.client.post(self.cancellation_url(appointment, english=True), follow=True)
        self.assertContains(response, "The appointment was cancelled.")
        self.assertContains(response, "Cancelled")
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)

        other_appointment = self.create_appointment(patient=self.other_patient)
        self.assertEqual(self.client.post(self.cancellation_url(other_appointment)).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.post(self.cancellation_url(other_appointment)).status_code, 302)

    def test_window_expiry_between_render_and_post_is_rejected(self):
        appointment = self.create_appointment(starts_at=timezone.now() + timedelta(hours=13))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.cancellation_url(appointment)).status_code, 200)
        appointment.starts_at = timezone.now() + timedelta(hours=11)
        appointment.ends_at = appointment.starts_at + timedelta(minutes=30)
        appointment.save(update_fields=["starts_at", "ends_at", "updated_at"])
        self.client.post(self.cancellation_url(appointment))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

    def test_staff_cancellation_remains_unaffected_by_patient_cutoff(self):
        appointment = self.create_appointment(starts_at=timezone.now() + timedelta(hours=1))
        cancelled = operations.cancel_appointment(
            appointment.pk,
            note="Staff-approved cancellation",
            actor=self.staff,
        )
        self.assertEqual(cancelled.status, Appointment.Status.CANCELLED)

    def test_patient_cancellation_post_enforces_csrf(self):
        appointment = self.create_appointment()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(
            csrf_client.post(self.cancellation_url(appointment)).status_code,
            403,
        )
