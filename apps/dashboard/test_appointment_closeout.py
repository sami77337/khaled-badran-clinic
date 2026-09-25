from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.booking import appointment_messages, operations
from apps.booking.models import Appointment, AppointmentMessageTemplate
from apps.clinic.models import Doctor, VisitType
from apps.core.models import AuditLog
from apps.core.views import APPROVED_CLINIC_PHONE
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

    def appointment(
        self, minutes, *, status=Appointment.Status.CONFIRMED, patient=None
    ):
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
        for status in (
            Appointment.Status.CANCELLED,
            Appointment.Status.COMPLETED,
            Appointment.Status.NO_SHOW,
        ):
            self.appointment(-180, status=status)
        original = list(Appointment.objects.values("pk", "status", "updated_at"))

        ids = set(
            operations.needs_classification_queryset(now=self.now).values_list(
                "id", flat=True
            )
        )

        self.assertEqual(ids, {past_confirmed.id, past_rescheduled.id})
        self.assertEqual(
            list(Appointment.objects.values("pk", "status", "updated_at")), original
        )
        self.assertFalse(AuditLog.objects.exists())
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

    def test_dashboard_keeps_appointment_messages_shortcut_when_follow_up_is_zero(self):
        self.client.force_login(self.staff)

        arabic = self.client.get(reverse("dashboard_home"))
        english = self.client.get(f"{reverse('dashboard_home')}?lang=en")
        settings_url = reverse("dashboard_appointment_message_settings")

        self.assertEqual(arabic.status_code, 200)
        self.assertEqual(english.status_code, 200)
        self.assertNotContains(arabic, "تحتاج متابعة (")
        self.assertNotContains(english, "Needs Follow-up (")
        self.assertContains(arabic, "رسائل المواعيد")
        self.assertContains(english, "Appointment Messages")
        self.assertContains(arabic, f'href="{settings_url}"')
        self.assertContains(english, f'href="{settings_url}?lang=en"')

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
        self.assertContains(
            arabic,
            "يمكنك إدراج معلومات الموعد تلقائيًا داخل الرسالة:",
        )
        self.assertContains(
            english,
            "You can insert appointment information automatically into the message:",
        )
        for label in ("اسم المريض", "تاريخ الموعد", "وقت الموعد", "هاتف العيادة"):
            self.assertContains(arabic, label)
        for label in (
            "Patient name",
            "Appointment date",
            "Appointment time",
            "Clinic phone",
        ):
            self.assertContains(english, label)
        for placeholder in (
            "{patient_name}",
            "{appointment_date}",
            "{appointment_time}",
            "{clinic_phone}",
        ):
            self.assertContains(arabic, placeholder)
            self.assertContains(english, placeholder)

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
        self.assertEqual(setting.updated_by, self.staff)
        original = list(AppointmentMessageTemplate.objects.values())

        invalid = self.client.post(
            url,
            {
                "event": AppointmentMessageTemplate.Event.NO_SHOW,
                "text_ar": "{secret_value}",
                "text_en": "{secret_value}",
            },
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(list(AppointmentMessageTemplate.objects.values()), original)

    def test_message_compose_prefills_rendered_default_and_opens_whatsapp(self):
        AppointmentMessageTemplate.objects.filter(event="arrived").update(
            is_active=True,
            text_ar="مرحبًا {patient_name} بتاريخ {appointment_date} الساعة {appointment_time}",
            text_en="Hello {patient_name} on {appointment_date} at {appointment_time}",
        )
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )
        response = self.client.get(f"{url}?event=arrived&lang=en")

        expected = (
            f"Hello Closeout Patient on "
            f"{timezone.localtime(appointment.starts_at):%Y-%m-%d} at "
            f"{timezone.localtime(appointment.starts_at):%H:%M}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_default_message"])
        self.assertEqual(response.context["message_text"], expected)
        self.assertContains(response, "No Message")
        self.assertContains(
            response,
            "Opening WhatsApp here does not mean the message was sent or delivered.",
        )
        self.assertNotContains(response, "Ready Message")
        self.assertNotContains(response, "Custom Message")

        opened = self.client.post(
            f"{url}?event=arrived&lang=en",
            {"event": "arrived", "message_text": expected},
        )
        self.assertEqual(opened.status_code, 302)
        parsed = urlsplit(opened.url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parsed.path, "/962791234567")
        self.assertEqual(parse_qs(parsed.query)["text"], [expected])

    def test_compose_fails_closed_when_stored_ready_template_is_corrupt(self):
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )

        for invalid in (
            "{broken",
            "{unknown}",
            "{patient_name.missing}",
            "{patient_name!r}",
            "{patient_name:}",
        ):
            with self.subTest(template=invalid):
                AppointmentMessageTemplate.objects.filter(event="arrived").update(
                    text_ar=invalid,
                    text_en=invalid,
                )
                response = self.client.get(f"{url}?event=arrived&lang=en")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["has_default_message"])
                self.assertEqual(response.context["message_text"], "")
                self.assertContains(
                    response, "No default message is active for this event."
                )
                settings = self.client.get(
                    reverse("dashboard_appointment_message_settings")
                )
                self.assertEqual(settings.status_code, 200)
                custom = self.client.post(
                    url,
                    {"event": "arrived", "message_text": "Synthetic custom message"},
                )
                self.assertEqual(custom.status_code, 302)
                self.assertEqual(urlsplit(custom.url).netloc, "wa.me")
        self.assertFalse(AuditLog.objects.exists())
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.ARRIVED)

    def test_custom_message_does_not_change_ready_template(self):
        AppointmentMessageTemplate.objects.filter(event="arrived").update(
            is_active=True,
            text_ar="النص الافتراضي",
            text_en="Default text",
        )
        setting = AppointmentMessageTemplate.objects.get(event="arrived")
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )
        response = self.client.post(
            url,
            {"event": "arrived", "message_text": "One-time custom message"},
        )

        self.assertEqual(response.status_code, 302)
        parsed = urlsplit(response.url)
        self.assertEqual(parsed.netloc, "wa.me")
        self.assertEqual(parse_qs(parsed.query)["text"], ["One-time custom message"])
        setting.refresh_from_db()
        self.assertEqual(setting.text_en, "Default text")
        self.assertEqual(setting.text_ar, "النص الافتراضي")
        self.assertFalse(AuditLog.objects.exists())

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
            {"event": "arrived", "message_text": "Message"},
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

    def test_staff_detail_hides_no_show_before_start_and_shows_after_start(self):
        future = self.appointment(60, status=Appointment.Status.CONFIRMED)
        past = self.appointment(-60, status=Appointment.Status.CONFIRMED)
        self.client.force_login(self.staff)

        future_response = self.client.get(
            reverse("staff_appointment_detail", kwargs={"appointment_id": future.id})
        )
        past_response = self.client.get(
            reverse("staff_appointment_detail", kwargs={"appointment_id": past.id})
        )

        self.assertEqual(future_response.status_code, 200)
        self.assertEqual(past_response.status_code, 200)
        self.assertFalse(future_response.context["can_mark_no_show"])
        self.assertTrue(past_response.context["can_mark_no_show"])
        self.assertNotContains(
            future_response,
            reverse("staff_appointment_no_show", kwargs={"appointment_id": future.id}),
        )
        self.assertContains(
            past_response,
            reverse("staff_appointment_no_show", kwargs={"appointment_id": past.id}),
        )

    def test_empty_queue_is_normal_in_both_languages(self):
        self.client.force_login(self.staff)
        url = reverse("dashboard_appointment_follow_up")
        for suffix, message, direction in (
            ("", "لا توجد مواعيد بحاجة إلى تصنيف حاليًا.", "rtl"),
            ("?lang=en", "No appointments currently need classification.", "ltr"),
        ):
            response = self.client.get(url + suffix)
            self.assertContains(response, message)
            self.assertContains(response, f'dir="{direction}"')
            self.assertEqual(response.context["page_obj"].paginator.count, 0)

    def test_operation_transition_matrix_preserves_terminal_states(self):
        minutes = -60
        for status in Appointment.Status.values:
            for action, allowed in (
                (operations.mark_arrived, {"confirmed", "rescheduled"}),
                (operations.mark_no_show, {"confirmed", "rescheduled"}),
                (operations.mark_completed, {"arrived"}),
            ):
                with self.subTest(status=status, action=action.__name__):
                    appointment = self.appointment(minutes, status=status)
                    minutes -= 60
                    if status in allowed:
                        action(
                            appointment.id,
                            actor=self.staff,
                            note="Synthetic internal reason",
                        )
                        self.assertEqual(appointment.status_history.count(), 1)
                    else:
                        with self.assertRaises(ValidationError):
                            action(
                                appointment.id,
                                actor=self.staff,
                                note="Synthetic internal reason",
                            )
                        appointment.refresh_from_db()
                        self.assertEqual(appointment.status, status)
                        self.assertEqual(appointment.status_history.count(), 0)

    def test_all_closeout_routes_deny_public_patient_and_inactive_staff(self):
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        patient_user = get_user_model().objects.create_user(
            username="synthetic-patient"
        )
        self.patient.user = patient_user
        self.patient.save(update_fields=["user"])
        inactive = get_user_model().objects.create_user(
            username="inactive-closeout", is_staff=True, is_active=False
        )
        urls = [
            reverse("dashboard_appointment_follow_up"),
            reverse("dashboard_appointment_message_settings"),
        ]
        urls += [
            reverse(name, kwargs={"appointment_id": appointment.id})
            for name in (
                "dashboard_appointment_message_compose",
                "dashboard_appointment_follow_up_arrived",
                "dashboard_appointment_follow_up_no_show",
                "dashboard_appointment_follow_up_complete",
            )
        ]
        original = list(AppointmentMessageTemplate.objects.values())
        for user in (None, patient_user, inactive):
            client = Client()
            if user:
                client.force_login(user)
            for url in urls:
                for method in (client.get, client.post):
                    with self.subTest(
                        user=getattr(user, "username", "public"),
                        url=url,
                        method=method.__name__,
                    ):
                        response = method(
                            url,
                            {"event": "arrived", "message_text": "Synthetic message"},
                        )
                        self.assertIn(response.status_code, (302, 403))
                        self.assertNotIn(
                            self.patient.full_name, response.content.decode()
                        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.ARRIVED)
        self.assertEqual(list(AppointmentMessageTemplate.objects.values()), original)

    def test_mutations_require_post_and_csrf(self):
        appointment = self.appointment(-60)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        for name in (
            "dashboard_appointment_follow_up_arrived",
            "dashboard_appointment_follow_up_no_show",
            "dashboard_appointment_follow_up_complete",
        ):
            url = reverse(name, kwargs={"appointment_id": appointment.id})
            self.assertEqual(client.get(url).status_code, 405)
            self.assertEqual(
                client.post(url, {"note": "Synthetic reason"}).status_code, 403
            )
        self.assertEqual(
            client.post(
                reverse("dashboard_appointment_message_settings"), {"event": "arrived"}
            ).status_code,
            403,
        )
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )
        self.assertEqual(
            client.post(
                url, {"event": "arrived", "message_text": "Synthetic message"}
            ).status_code,
            403,
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

    def test_default_messages_compose_for_each_event_and_language(self):
        self.client.force_login(self.staff)
        for event, status in (
            ("arrived", Appointment.Status.ARRIVED),
            ("no_show", Appointment.Status.NO_SHOW),
        ):
            appointment = self.appointment(-60, status=status)
            url = reverse(
                "dashboard_appointment_message_compose",
                kwargs={"appointment_id": appointment.id},
            )
            for language, suffix in (("ar", ""), ("en", "&lang=en")):
                response = self.client.get(f"{url}?event={event}{suffix}")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["has_default_message"])
                rendered = appointment_messages.render_ready_message(
                    appointment,
                    event=event,
                    language=language,
                    clinic_phone=APPROVED_CLINIC_PHONE["display"],
                )
                self.assertEqual(response.context["message_text"], rendered)

    def test_invalid_phone_and_event_fail_closed_for_get_and_post(self):
        appointment = self.appointment(-30, status=Appointment.Status.ARRIVED)
        Appointment.objects.filter(pk=appointment.pk).update(
            whatsapp_phone_e164="invalid-phone"
        )
        self.client.force_login(self.staff)
        url = reverse(
            "dashboard_appointment_message_compose",
            kwargs={"appointment_id": appointment.id},
        )
        for method in (self.client.get, self.client.post):
            response = method(
                url, {"event": "arrived", "message_text": "Synthetic message"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["whatsapp_available"])
            for event in ("no_show", "completed", "unknown"):
                self.assertEqual(
                    method(
                        url, {"event": event, "message_text": "Synthetic message"}
                    ).status_code,
                    404,
                )

    def test_staff_can_disable_defaults_and_no_delivery_fields_exist(self):
        self.client.force_login(self.staff)
        setting = AppointmentMessageTemplate.objects.get(event="arrived")
        response = self.client.post(
            reverse("dashboard_appointment_message_settings"),
            {
                "event": "arrived",
                "text_ar": setting.text_ar,
                "text_en": setting.text_en,
            },
        )
        self.assertEqual(response.status_code, 302)
        setting.refresh_from_db()
        self.assertFalse(setting.is_active)
        self.assertEqual(setting.updated_by, self.staff)
        self.assertFalse(
            any(
                "sent" in field.name or "deliver" in field.name
                for field in setting._meta.fields
            )
        )
