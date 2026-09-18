from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog
from apps.patients.models import Patient

from .appointment_messages import (
    get_ready_message_template,
    render_ready_message,
    save_appointment_message_template,
)
from .message_template_validation import validate_appointment_message_template
from .models import Appointment, AppointmentMessageTemplate


class AppointmentMessageBackendTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="appointment-message-staff",
            password="synthetic-password",
            is_staff=True,
        )
        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب تجريبي",
            full_name_en="Synthetic Doctor",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="اختصاص تجريبي",
            specialty_en="Synthetic specialty",
            is_active=True,
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="زيارة تجريبية",
            name_en="Synthetic visit",
            duration_minutes=30,
            is_active=True,
        )
        self.patient = Patient.objects.create(
            full_name="Synthetic Patient",
            phone_raw="0791234000",
            phone_e164="+962791234000",
        )
        starts_at = timezone.now().replace(second=0, microsecond=0)
        self.appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            visit_type=self.visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=Appointment.Status.ARRIVED,
        )

    def test_approved_defaults_are_ready_in_both_languages(self):
        self.assertEqual(AppointmentMessageTemplate.objects.count(), 2)
        for setting in AppointmentMessageTemplate.objects.all():
            self.assertTrue(setting.is_active)
            for language in ("ar", "en"):
                with self.subTest(event=setting.event, language=language):
                    self.assertEqual(
                        get_ready_message_template(setting.event, language),
                        getattr(setting, f"text_{language}"),
                    )
                    self.assertTrue(getattr(setting, f"text_{language}"))

    def test_template_validation_accepts_only_allowlisted_placeholders(self):
        validate_appointment_message_template(
            "Hello {patient_name}, {appointment_date} {appointment_time} {clinic_phone}"
        )
        for invalid in (
            "{unknown_value}",
            "{patient_name!r}",
            "{patient_name!s}",
            "{patient_name:}",
            "{patient_name:>20}",
            "{patient_name:{clinic_phone}}",
            "{patient_name.upper}",
            "{patient_name[0]}",
            "{patient_name",
            "patient_name}",
            "{}",
            "{{patient_name}}",
        ):
            with self.subTest(template=invalid), self.assertRaises(ValidationError):
                validate_appointment_message_template(invalid)

    def test_active_setting_requires_both_languages(self):
        original = list(AppointmentMessageTemplate.objects.values())
        with self.assertRaises(ValidationError):
            save_appointment_message_template(
                event=AppointmentMessageTemplate.Event.ARRIVED,
                is_active=True,
                text_ar="تم الوصول {patient_name}",
                text_en="",
                actor=self.staff,
            )
        self.assertEqual(list(AppointmentMessageTemplate.objects.values()), original)

    def test_save_is_audited_without_copying_template_text_into_audit_metadata(self):
        setting = save_appointment_message_template(
            event=AppointmentMessageTemplate.Event.NO_SHOW,
            is_active=False,
            text_ar="لم يتم تسجيل الحضور {patient_name}",
            text_en="Attendance was not recorded for {patient_name}",
            actor=self.staff,
        )
        audit = AuditLog.objects.get(
            app_label="booking",
            model_name="AppointmentMessageTemplate",
            object_id=str(setting.pk),
        )
        self.assertEqual(
            audit.metadata["event"], AppointmentMessageTemplate.Event.NO_SHOW
        )
        self.assertFalse(audit.metadata["is_active"])
        self.assertNotIn("text_ar", audit.metadata)
        self.assertNotIn("text_en", audit.metadata)
        self.assertEqual(audit.user, self.staff)
        self.assertEqual(setting.updated_by, self.staff)
        self.assertEqual(set(audit.metadata), {"event", "is_active", "changed_fields"})

    def test_ready_message_renders_allowed_values_without_sending_or_mutating_appointment(
        self,
    ):
        save_appointment_message_template(
            event=AppointmentMessageTemplate.Event.ARRIVED,
            is_active=True,
            text_ar="مرحبًا {patient_name} - {appointment_date} {appointment_time} - {clinic_phone}",
            text_en="Hello {patient_name} - {appointment_date} {appointment_time} - {clinic_phone}",
            actor=self.staff,
        )
        original_status = self.appointment.status
        rendered = render_ready_message(
            self.appointment,
            event=AppointmentMessageTemplate.Event.ARRIVED,
            language="en",
            clinic_phone="+962798898510",
        )
        self.assertIn("Synthetic Patient", rendered)
        self.assertIn("+962798898510", rendered)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, original_status)
        self.assertEqual(self.appointment.status_history.count(), 0)

    def test_inactive_setting_never_produces_ready_message(self):
        save_appointment_message_template(
            event=AppointmentMessageTemplate.Event.NO_SHOW,
            is_active=False,
            text_ar="نص {patient_name}",
            text_en="Text {patient_name}",
            actor=self.staff,
        )
        self.assertEqual(
            render_ready_message(
                self.appointment,
                event=AppointmentMessageTemplate.Event.NO_SHOW,
                language="ar",
                clinic_phone="+962798898510",
            ),
            "",
        )
