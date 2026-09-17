from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.booking import operations
from apps.booking.models import Appointment, AppointmentMessageTemplate
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
        self.assertIn("event=arrived", response.url)
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
        self.assertIn("event=no_show", response.url)
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

    def test_message_settings_are_staff_only_and_bilingual(self):
        url = reverse("dashboard_appointment_message_settings")
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(self.staff)
        arabic = self.client.get(url)
        english = self.client.get(f"{url}?lang=en")
        self.assertEqual(arabic.status_code, 200)
        self.assertEqual(english.status_code, 200)
        self.assertContains(arabic, "رسائل المواعيد")
        self.assertContains(english, "Appointment Messages")

    def test_message_settings_save_valid_templates_and_reject_bad_placeholder(self):
        self.client.force_login(self.staff)
        url = reverse("dashboard_appointment_message_settings")
        valid = self.client.post(
            url,
            {
                "event": AppointmentMessageTemplate.Event.ARRIVED,
                "is_active": "on",
                "text_ar": "مرحبًا {patient_name} في {appointment_time}",
                "text_en": "Hello {patient_name} at {appointment_time}",
            },
        )
        self.assertEqual(valid.status_code, 302)
        setting = AppointmentMessageTemplate.objects.get(
            event=AppointmentMessageTemplate.Event.ARRIVED
        )
        self.assertTrue(setting.is_active)

        invalid = self.client.post(
            url,
            {
                "event": AppointmentMessageTemplate.Event.NO_SHOW,
                "text_ar": "{secret_value}",
                "text_en": "{secret_value}",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(
            AppointmentMessageTemplate.objects.filter(
                event=AppointmentMessageTemplate.Event.NO_SHOW
            ).exists()
        )

    def test_ready_message_compose_is_manual_and_uses_validated_whatsapp_url(self):
        AppointmentMessageTemplate.objects.create(
            event=AppointmentMessageTemplate.Event.ARRIVED,
            is_active=True,
            text_ar="مرحبًا {patient_name}",
            text_en="Hello {patient_name}",
        )
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )
        response = self.client.get(f"{url}?event=arrived&lang=en")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Message")
        self.assertContains(response, "Opening WhatsApp here does not mean the message was sent or delivered.")
        ready_url = response.context["ready_en_url"]
        parsed = urlsplit(ready_url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parsed.path, "/962791234567")
        self.assertEqual(parse_qs(parsed.query)["text"], ["Hello Closeout Patient"])

    def test_custom_message_does_not_change_ready_template(self):
        setting = AppointmentMessageTemplate.objects.create(
            event=AppointmentMessageTemplate.Event.ARRIVED,
            is_active=True,
            text_ar="النص الافتراضي",
            text_en="Default text",
        )
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )
        response = self.client.post(
            url,
            {"event": "arrived", "custom_message": "One-time custom message"},
        )

        self.assertEqual(response.status_code, 302)
        parsed = urlsplit(response.url)
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parse_qs(parsed.query)["text"], ["One-time custom message"])
        setting.refresh_from_db()
        self.assertEqual(setting.text_en, "Default text")
        self.assertEqual(setting.text_ar, "النص الافتراضي")

    def test_compose_fails_closed_for_missing_phone_and_status_mismatch(self):
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        self.patient.phone_raw = ""
        self.patient.phone_e164 = ""
        self.patient.whatsapp_phone_raw = ""
        self.patient.whatsapp_phone_e164 = ""
        self.patient.save(
            update_fields=[
                "phone_raw",
                "phone_e164",
                "whatsapp_phone_raw",
                "whatsapp_phone_e164",
            ]
        )
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )
        response = self.client.post(
            url,
            {"event": "arrived", "custom_message": "Message"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["whatsapp_available"])

        confirmed = self.appointment(-60, status=Appointment.Status.CONFIRMED)
        mismatch_url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": confirmed.id},
        )
        self.assertEqual(
            self.client.get(f"{mismatch_url}?event=arrived").status_code,
            404,
        )
