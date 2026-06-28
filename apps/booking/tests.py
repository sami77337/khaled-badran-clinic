from datetime import datetime, time, timedelta

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.booking.forms import PublicBookingForm
from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.booking.phone import normalize_phone
from apps.booking import services
from apps.clinic.models import ClosedDay, Doctor, DoctorSchedule, VisitType
from apps.core.models import SystemSetting
from apps.patients.models import Patient


def aware(year=2026, month=1, day=5, hour=8, minute=0):
    return timezone.make_aware(
        datetime(year, month, day, hour, minute),
        timezone.get_current_timezone(),
    )


class BookingTestDataMixin:
    def create_doctor(self):
        return Doctor.objects.create(
            full_name_ar="خالد حسان بدران",
            full_name_en="Khaled Hassan Badran",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="استشاري الأنف والأذن والحنجرة",
            specialty_en="ENT consultant",
            is_active=True,
        )

    def create_visit_type(self, doctor=None, duration=30, is_active=True):
        return VisitType.objects.create(
            doctor=doctor,
            name_ar="كشف جديد",
            name_en="New consultation",
            duration_minutes=duration,
            is_active=is_active,
        )

    def create_schedule(self, doctor, weekday=0, start=time(10, 0), end=time(12, 0), is_active=True):
        return DoctorSchedule.objects.create(
            doctor=doctor,
            weekday=weekday,
            start_time=start,
            end_time=end,
            is_active=is_active,
        )

    def create_patient(self):
        return Patient.objects.create(
            full_name="Test Patient",
            phone_raw="0791234567",
            phone_e164="+962791234567",
        )

    def set_setting(self, key, value, value_type=SystemSetting.ValueType.INTEGER):
        return SystemSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": str(value).lower() if isinstance(value, bool) else str(value),
                "value_type": value_type,
            },
        )[0]

    def setup_public_booking(self, *, min_lead=0, max_days=30, interval=30, duration=30):
        doctor = Doctor.objects.filter(is_active=True).order_by("display_order", "id").first()
        if doctor is None:
            doctor = self.create_doctor()
        visit_type = self.create_visit_type(doctor=doctor, duration=duration)
        tomorrow = timezone.localdate() + timedelta(days=1)
        self.create_schedule(doctor, weekday=tomorrow.weekday(), start=time(9, 0), end=time(12, 0))
        self.set_setting(SystemSetting.BOOKING_ENABLED, True, SystemSetting.ValueType.BOOLEAN)
        self.set_setting(SystemSetting.BOOKING_MIN_LEAD_MINUTES, min_lead)
        self.set_setting(SystemSetting.BOOKING_MAX_DAYS_AHEAD, max_days)
        self.set_setting(SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES, interval)
        self.set_setting(SystemSetting.APPOINTMENT_REMINDER_OFFSET_MINUTES, 180)
        slots = services.generate_available_slots(visit_type, target_date=tomorrow, doctor=doctor)
        return doctor, visit_type, tomorrow, slots[0]


class BookingServiceTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.doctor = self.create_doctor()
        self.visit_type = self.create_visit_type(doctor=self.doctor)
        self.settings = services.BookingSettings(
            enabled=True,
            min_lead_minutes=60,
            max_days_ahead=30,
            slot_interval_minutes=30,
            reminder_offset_minutes=180,
        )
        self.now = aware(2026, 1, 5, 8, 0)

    def test_generates_slots_from_schedule(self):
        self.create_schedule(self.doctor, weekday=0, start=time(10, 0), end=time(12, 0))

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=self.now.date(),
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertEqual([slot.local_time.strftime("%H:%M") for slot in slots], ["10:00", "10:30", "11:00", "11:30"])

    def test_no_slots_on_closed_day(self):
        self.create_schedule(self.doctor, weekday=0)
        ClosedDay.objects.create(doctor=self.doctor, date=self.now.date(), reason_en="Closed", is_active=True)

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=self.now.date(),
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertEqual(slots, [])

    def test_no_past_slots(self):
        self.create_schedule(self.doctor, weekday=0, start=time(8, 0), end=time(11, 0))
        now = aware(2026, 1, 5, 10, 15)
        settings = services.BookingSettings(True, 0, 30, 15, 180)

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=now.date(),
            now=now,
            settings=settings,
            doctor=self.doctor,
        )

        self.assertTrue(all(slot.starts_at > now for slot in slots))

    def test_respects_min_lead_time(self):
        self.create_schedule(self.doctor, weekday=0, start=time(8, 30), end=time(12, 0))

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=self.now.date(),
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertTrue(all(slot.starts_at >= self.now + timedelta(minutes=60) for slot in slots))

    def test_respects_max_days_ahead(self):
        future_day = self.now.date() + timedelta(days=31)
        self.create_schedule(self.doctor, weekday=future_day.weekday())

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=future_day,
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertEqual(slots, [])

    def test_respects_visit_type_duration(self):
        long_visit = self.create_visit_type(doctor=self.doctor, duration=60)
        self.create_schedule(self.doctor, weekday=0, start=time(10, 0), end=time(11, 0))

        slots = services.generate_available_slots(
            long_visit,
            target_date=self.now.date(),
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].ends_at - slots[0].starts_at, timedelta(minutes=60))

    def test_excludes_existing_appointment_overlap(self):
        self.create_schedule(self.doctor, weekday=0, start=time(10, 0), end=time(12, 0))
        patient = self.create_patient()
        Appointment.objects.create(
            doctor=self.doctor,
            patient=patient,
            visit_type=self.visit_type,
            starts_at=aware(2026, 1, 5, 10, 30),
            ends_at=aware(2026, 1, 5, 11, 0),
        )

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=self.now.date(),
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertNotIn("10:30", [slot.local_time.strftime("%H:%M") for slot in slots])

    def test_excludes_inactive_schedule(self):
        self.create_schedule(self.doctor, weekday=0, is_active=False)

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=self.now.date(),
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertEqual(slots, [])

    def test_excludes_inactive_visit_type(self):
        inactive_visit = self.create_visit_type(doctor=self.doctor, is_active=False)
        self.create_schedule(self.doctor, weekday=0)

        slots = services.generate_available_slots(
            inactive_visit,
            target_date=self.now.date(),
            now=self.now,
            settings=self.settings,
            doctor=self.doctor,
        )

        self.assertEqual(slots, [])

    def test_booking_disabled_returns_no_slots_and_blocks_validation(self):
        self.create_schedule(self.doctor, weekday=0)
        disabled = services.BookingSettings(False, 60, 30, 30, 180)

        slots = services.generate_available_slots(
            self.visit_type,
            target_date=self.now.date(),
            now=self.now,
            settings=disabled,
            doctor=self.doctor,
        )

        self.assertEqual(slots, [])
        with self.assertRaises(ValidationError):
            services.validate_public_booking_request(
                self.visit_type,
                aware(2026, 1, 5, 10, 0),
                settings=disabled,
                doctor=self.doctor,
                now=self.now,
            )

    def test_appointment_end_time_and_reminder_offset_are_computed(self):
        _, visit_type, _, slot = self.setup_public_booking(min_lead=0, interval=30)

        appointment = services.create_public_appointment(
            full_name="Test Patient",
            phone_raw="0791234567",
            visit_type_id=visit_type.id,
            starts_at=slot.value,
        )

        self.assertEqual(appointment.ends_at - appointment.starts_at, timedelta(minutes=30))
        self.assertEqual(appointment.reminder_offset, timedelta(hours=3))
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)


class PhoneNormalizationTests(TestCase):
    def test_local_jordan_mobile_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("0791234567"), "+962791234567")

    def test_local_jordan_mobile_with_spaces_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("079 123 4567"), "+962791234567")

    def test_local_jordan_mobile_with_dashes_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("079-123-4567"), "+962791234567")

    def test_arabic_user_spacing_in_079_format_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("079 123 45 67"), "+962791234567")

    def test_00962_number_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("00962791234567"), "+962791234567")

    def test_00962_number_with_spaces_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("00962 79 123 4567"), "+962791234567")

    def test_plus_962_number_stays_e164(self):
        self.assertEqual(normalize_phone("+962791234567"), "+962791234567")

    def test_plus_962_number_with_spaces_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("+962 79 123 4567"), "+962791234567")

    def test_962_prefix_normalizes_to_e164(self):
        self.assertEqual(normalize_phone("962791234567"), "+962791234567")

    def test_invalid_short_number_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_phone("07912")

    def test_invalid_alphabetic_phone_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_phone("phone-number")

    def test_non_jordanian_without_country_code_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_phone("201001234567")

    def test_international_plus_number_accepted_when_plausible(self):
        self.assertEqual(normalize_phone("+442071234567"), "+442071234567")

    def test_international_without_plus_rejected(self):
        with self.assertRaises(ValidationError):
            normalize_phone("442071234567")


class PublicBookingFormTests(BookingTestDataMixin, TestCase):
    def valid_form_data(self):
        _, visit_type, _, slot = self.setup_public_booking()
        return {
            "full_name": "Test Patient",
            "phone": "0791234567",
            "same_as_phone": "on",
            "visit_type": str(visit_type.id),
            "starts_at": slot.value,
            "booking_note": "",
        }

    def test_valid_form_validates_normalized_phone(self):
        form = PublicBookingForm(data=self.valid_form_data())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.normalized_phone, "+962791234567")

    def test_missing_name_invalid(self):
        data = self.valid_form_data()
        data["full_name"] = ""

        form = PublicBookingForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("full_name", form.errors)

    def test_missing_phone_invalid(self):
        data = self.valid_form_data()
        data["phone"] = ""

        form = PublicBookingForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_inactive_visit_type_invalid(self):
        data = self.valid_form_data()
        inactive = self.create_visit_type(is_active=False)
        data["visit_type"] = str(inactive.id)

        form = PublicBookingForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("visit_type", form.errors)

    def test_stale_slot_invalid(self):
        data = self.valid_form_data()
        visit_type = VisitType.objects.get(id=data["visit_type"])
        patient = self.create_patient()
        starts_at = services.parse_slot_datetime(data["starts_at"])
        Appointment.objects.create(
            doctor=visit_type.doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=visit_type.duration_minutes),
        )

        form = PublicBookingForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("This appointment time is no longer available.", str(form.errors))

    def test_invalid_phone_invalid(self):
        data = self.valid_form_data()
        data["phone"] = "12345"

        form = PublicBookingForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_note_is_optional(self):
        data = self.valid_form_data()
        data.pop("booking_note")

        form = PublicBookingForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)


class PublicBookingViewTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.doctor, self.visit_type, self.tomorrow, self.slot = self.setup_public_booking()

    def test_book_home_returns_200(self):
        response = self.client.get(reverse("book"))

        self.assertEqual(response.status_code, 200)

    def test_english_book_home_returns_200(self):
        response = self.client.get(reverse("book_en"))

        self.assertEqual(response.status_code, 200)

    def test_visit_type_step_returns_200(self):
        response = self.client.get(reverse("booking_visit_type"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "كشف جديد")

    def test_slot_step_returns_200_with_seeded_schedule(self):
        response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.slot.local_time.strftime("%H:%M"))

    def test_confirm_get_returns_200_for_valid_slot(self):
        response = self.client.get(
            reverse("booking_confirm"),
            {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تأكيد الموعد")

    def test_valid_post_creates_exactly_one_patient_and_appointment(self):
        response = self.client.post(
            reverse("booking_confirm"),
            {
                "full_name": "Test Patient",
                "phone": "0791234567",
                "same_as_phone": "on",
                "visit_type": str(self.visit_type.id),
                "starts_at": self.slot.value,
                "booking_note": "Please call before appointment.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Appointment.objects.count(), 1)
        appointment = Appointment.objects.get()
        self.assertIn(str(appointment.public_token), response["Location"])
        self.assertEqual(appointment.patient.phone_e164, "+962791234567")
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

    def test_valid_booking_redirects_to_token_success_url(self):
        response = self.client.post(
            reverse("booking_confirm"),
            {
                "full_name": "Test Patient",
                "phone": "0791234567",
                "same_as_phone": "on",
                "visit_type": str(self.visit_type.id),
                "starts_at": self.slot.value,
            },
        )

        appointment = Appointment.objects.get()
        self.assertRedirects(
            response,
            reverse("booking_success", kwargs={"public_token": appointment.public_token}),
            fetch_redirect_response=False,
        )

    def test_duplicate_stale_post_does_not_double_book(self):
        post_data = {
            "full_name": "Test Patient",
            "phone": "0791234567",
            "same_as_phone": "on",
            "visit_type": str(self.visit_type.id),
            "starts_at": self.slot.value,
            "booking_note": "",
        }

        self.client.post(reverse("booking_confirm"), post_data)
        response = self.client.post(reverse("booking_confirm"), post_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertContains(response, "This appointment time is no longer available.")

    def test_exact_duplicate_database_constraint_blocks_same_status_slot(self):
        patient = self.create_patient()
        Appointment.objects.create(
            doctor=self.doctor,
            patient=patient,
            visit_type=self.visit_type,
            starts_at=self.slot.starts_at,
            ends_at=self.slot.ends_at,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                doctor=self.doctor,
                patient=patient,
                visit_type=self.visit_type,
                starts_at=self.slot.starts_at,
                ends_at=self.slot.ends_at,
            )

    def test_visiting_public_pages_alone_does_not_create_appointment(self):
        self.client.get(reverse("book"))
        self.client.get(reverse("booking_visit_type"))
        self.client.get(reverse("booking_slots"), {"visit_type": self.visit_type.id})

        self.assertEqual(Appointment.objects.count(), 0)

    def test_success_page_returns_200(self):
        appointment = services.create_public_appointment(
            full_name="Test Patient",
            phone_raw="0791234567",
            visit_type_id=self.visit_type.id,
            starts_at=self.slot.value,
        )

        response = self.client.get(reverse("booking_success", kwargs={"public_token": appointment.public_token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, appointment.confirmation_reference)

    def test_numeric_success_url_no_longer_resolves(self):
        appointment = services.create_public_appointment(
            full_name="Test Patient",
            phone_raw="0791234567",
            visit_type_id=self.visit_type.id,
            starts_at=self.slot.value,
        )

        response = self.client.get(f"/book/success/{appointment.id}/")

        self.assertEqual(response.status_code, 404)

    def test_invalid_uuid_success_url_returns_404(self):
        response = self.client.get("/book/success/not-a-uuid/")

        self.assertEqual(response.status_code, 404)

    def test_public_success_page_does_not_show_internal_numeric_id_label(self):
        appointment = services.create_public_appointment(
            full_name="Test Patient",
            phone_raw="0791234567",
            visit_type_id=self.visit_type.id,
            starts_at=self.slot.value,
        )

        response = self.client.get(reverse("booking_success", kwargs={"public_token": appointment.public_token}))

        self.assertNotContains(response, "Appointment ID")
        self.assertNotContains(response, "رقم الموعد")
        self.assertNotContains(response, "booking_note")

    def test_english_success_page_returns_200(self):
        appointment = services.create_public_appointment(
            full_name="Test Patient",
            phone_raw="0791234567",
            visit_type_id=self.visit_type.id,
            starts_at=self.slot.value,
        )

        response = self.client.get(reverse("booking_success_en", kwargs={"public_token": appointment.public_token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Appointment")

    def test_inactive_doctor_cannot_receive_new_booking(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("booking_confirm"),
            {
                "full_name": "Test Patient",
                "phone": "0791234567",
                "same_as_phone": "on",
                "visit_type": str(self.visit_type.id),
                "starts_at": self.slot.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_closed_day_blocks_public_slot_display(self):
        ClosedDay.objects.create(doctor=self.doctor, date=self.tomorrow, is_active=True)

        response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لا توجد أوقات متاحة")

    def test_min_lead_time_blocks_near_slots(self):
        self.set_setting(SystemSetting.BOOKING_MIN_LEAD_MINUTES, 60 * 24 * 7)

        response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لا توجد أوقات متاحة")

    def test_max_days_ahead_blocks_far_slots(self):
        far_day = timezone.localdate() + timedelta(days=60)

        response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id, "date": far_day.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "لا توجد أوقات متاحة")

    def test_no_whatsapp_models_or_actions_are_invoked(self):
        self.client.post(
            reverse("booking_confirm"),
            {
                "full_name": "Test Patient",
                "phone": "0791234567",
                "same_as_phone": "on",
                "visit_type": str(self.visit_type.id),
                "starts_at": self.slot.value,
            },
        )

        whatsapp_models = list(apps.get_app_config("whatsapp").get_models())
        self.assertEqual(whatsapp_models, [])

    def test_no_patient_portal_or_upload_routes_are_added(self):
        portal_response = self.client.get("/portal/")
        uploads_response = self.client.get("/uploads/")

        self.assertEqual(portal_response.status_code, 404)
        self.assertEqual(uploads_response.status_code, 404)

    def test_booking_disabled_shows_unavailable_and_blocks_post(self):
        self.set_setting(SystemSetting.BOOKING_ENABLED, False, SystemSetting.ValueType.BOOLEAN)

        response = self.client.get(reverse("book"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "الحجز غير متاح")

        post_response = self.client.post(
            reverse("booking_confirm"),
            {
                "full_name": "Test Patient",
                "phone": "0791234567",
                "same_as_phone": "on",
                "visit_type": str(self.visit_type.id),
                "starts_at": self.slot.value,
            },
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)


class BookingModelAndAdminBehaviorTests(BookingTestDataMixin, TestCase):
    def test_appointment_default_status_is_confirmed(self):
        doctor, visit_type, _, slot = self.setup_public_booking()
        patient = self.create_patient()
        appointment = Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
        )

        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertIsNotNone(appointment.public_token)
        self.assertEqual(len(appointment.confirmation_reference), 8)

    def test_status_history_can_record_change(self):
        doctor, visit_type, _, slot = self.setup_public_booking()
        patient = self.create_patient()
        appointment = Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
        )

        history = AppointmentStatusHistory.objects.create(
            appointment=appointment,
            old_status=Appointment.Status.CONFIRMED,
            new_status=Appointment.Status.CANCELLED,
            note="Patient called.",
        )

        self.assertEqual(str(history), f"{appointment.id}: confirmed -> cancelled")

    def test_appointment_ends_after_start_validation_remains_active(self):
        doctor, visit_type, _, slot = self.setup_public_booking()
        patient = self.create_patient()
        appointment = Appointment(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=slot.starts_at,
            ends_at=slot.starts_at,
        )

        with self.assertRaises(ValidationError):
            appointment.full_clean()

    def test_patient_raw_and_normalized_phones_are_stored(self):
        patient = Patient.objects.create(
            full_name="Test Patient",
            phone_raw="0791234567",
            phone_e164="+962791234567",
            whatsapp_phone_raw="0791234567",
            whatsapp_phone_e164="+962791234567",
        )

        self.assertEqual(patient.phone_raw, "0791234567")
        self.assertEqual(patient.phone_e164, "+962791234567")
        self.assertEqual(patient.whatsapp_phone_e164, "+962791234567")

    def test_system_setting_defaults_are_usable(self):
        settings = services.get_booking_settings()

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.min_lead_minutes, 180)
        self.assertEqual(settings.max_days_ahead, 30)
        self.assertEqual(settings.slot_interval_minutes, 15)
        self.assertEqual(settings.reminder_offset_minutes, 180)
