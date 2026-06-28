from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.booking.forms import PublicBookingForm
from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.booking.phone import normalize_phone
from apps.booking import operations, services
from apps.clinic.models import ClosedDay, Doctor, DoctorSchedule, VisitType
from apps.core.models import AuditLog, SystemSetting
from apps.patients.models import Patient


def aware(year=2026, month=1, day=5, hour=8, minute=0):
    return timezone.make_aware(
        datetime(year, month, day, hour, minute),
        timezone.get_current_timezone(),
    )


class BookingTestDataMixin:
    def create_user(self, username="patient-user", is_staff=False):
        return get_user_model().objects.create_user(
            username=username,
            email=f"{username}@example.test",
            password="test-password",
            is_staff=is_staff,
        )

    def create_staff_user(self, username="staff-user"):
        return self.create_user(username=username, is_staff=True)

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

    def future_aware(self, days=1, hour=9, minute=0):
        day = timezone.localdate() + timedelta(days=days)
        return timezone.make_aware(
            datetime.combine(day, time(hour, minute)),
            timezone.get_current_timezone(),
        )

    def create_appointment(
        self,
        *,
        doctor=None,
        visit_type=None,
        patient=None,
        starts_at=None,
        status=Appointment.Status.CONFIRMED,
    ):
        doctor = doctor or self.create_doctor()
        visit_type = visit_type or self.create_visit_type(doctor=doctor)
        patient = patient or self.create_patient()
        starts_at = starts_at or self.future_aware()
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=visit_type.duration_minutes),
            status=status,
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


class StaffAuthorizationTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.appointment = self.create_appointment()
        self.list_url = reverse("staff_appointment_list")
        self.detail_url = reverse("staff_appointment_detail", kwargs={"appointment_id": self.appointment.id})

    def test_anonymous_cannot_access_staff_appointment_list(self):
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_anonymous_cannot_access_staff_detail(self):
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_anonymous_cannot_perform_staff_operations(self):
        operation_urls = [
            reverse("staff_appointment_cancel", kwargs={"appointment_id": self.appointment.id}),
            reverse("staff_appointment_reschedule", kwargs={"appointment_id": self.appointment.id}),
            reverse("staff_appointment_arrived", kwargs={"appointment_id": self.appointment.id}),
            reverse("staff_appointment_complete", kwargs={"appointment_id": self.appointment.id}),
            reverse("staff_appointment_no_show", kwargs={"appointment_id": self.appointment.id}),
        ]

        for url in operation_urls:
            with self.subTest(url=url):
                response = self.client.post(url, {"note": "staff note"})

                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])

    def test_non_staff_user_cannot_access_staff_appointment_list(self):
        self.client.force_login(self.create_user())

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 403)

    def test_non_staff_user_cannot_perform_staff_operation(self):
        self.client.force_login(self.create_user())

        response = self.client.post(
            reverse("staff_appointment_cancel", kwargs={"appointment_id": self.appointment.id}),
            {"note": "Patient called."},
        )

        self.assertEqual(response.status_code, 403)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CONFIRMED)

    def test_staff_user_can_access_appointment_list(self):
        self.client.force_login(self.create_staff_user())

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.appointment.patient.full_name)

    def test_staff_user_can_access_appointment_detail(self):
        self.client.force_login(self.create_staff_user())

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status history")
        self.assertContains(response, "Audit events")


class AppointmentOperationServiceTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff_user()
        self.appointment = self.create_appointment()

    def test_public_booking_creates_audit_and_initial_status_history(self):
        _, visit_type, _, slot = self.setup_public_booking()

        appointment = services.create_public_appointment(
            full_name="Test Patient",
            phone_raw="0791234567",
            visit_type_id=visit_type.id,
            starts_at=slot.value,
        )

        self.assertTrue(
            AppointmentStatusHistory.objects.filter(
                appointment=appointment,
                old_status="",
                new_status=Appointment.Status.CONFIRMED,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.CREATE,
                object_id=str(appointment.id),
                metadata__public_token=str(appointment.public_token),
            ).exists()
        )

    def test_staff_can_cancel_confirmed_appointment(self):
        operations.cancel_appointment(self.appointment.id, actor=self.staff, note="Patient called.")

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)

    def test_cancellation_requires_note(self):
        with self.assertRaises(ValidationError):
            operations.cancel_appointment(self.appointment.id, actor=self.staff, note="")

    def test_cancellation_creates_status_history_and_audit_log(self):
        operations.cancel_appointment(self.appointment.id, actor=self.staff, note="Patient called.")

        self.assertTrue(
            AppointmentStatusHistory.objects.filter(
                appointment=self.appointment,
                old_status=Appointment.Status.CONFIRMED,
                new_status=Appointment.Status.CANCELLED,
                changed_by=self.staff,
            ).exists()
        )
        audit = AuditLog.objects.get(object_id=str(self.appointment.id), action=AuditLog.Action.STATUS_CHANGE)
        self.assertEqual(audit.metadata["old_status"], Appointment.Status.CONFIRMED)
        self.assertEqual(audit.metadata["new_status"], Appointment.Status.CANCELLED)
        self.assertEqual(audit.metadata["actor_user_id"], self.staff.id)

    def test_staff_can_mark_arrived(self):
        operations.mark_arrived(self.appointment.id, actor=self.staff, note="Checked in.")

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.ARRIVED)
        self.assertTrue(
            AppointmentStatusHistory.objects.filter(
                appointment=self.appointment,
                new_status=Appointment.Status.ARRIVED,
            ).exists()
        )
        self.assertTrue(AuditLog.objects.filter(object_id=str(self.appointment.id)).exists())

    def test_staff_can_mark_completed_after_arrived(self):
        operations.mark_arrived(self.appointment.id, actor=self.staff)
        operations.mark_completed(self.appointment.id, actor=self.staff, note="Visit completed.")

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.COMPLETED)

    def test_completed_creates_history_and_audit(self):
        operations.mark_arrived(self.appointment.id, actor=self.staff)
        operations.mark_completed(self.appointment.id, actor=self.staff, note="Done.")

        self.assertTrue(
            AppointmentStatusHistory.objects.filter(
                appointment=self.appointment,
                old_status=Appointment.Status.ARRIVED,
                new_status=Appointment.Status.COMPLETED,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(self.appointment.id),
                metadata__new_status=Appointment.Status.COMPLETED,
            ).exists()
        )

    def test_completed_directly_from_confirmed_is_rejected(self):
        with self.assertRaises(ValidationError):
            operations.mark_completed(self.appointment.id, actor=self.staff)

    def test_cancelled_appointment_cannot_be_completed(self):
        operations.cancel_appointment(self.appointment.id, actor=self.staff, note="Patient called.")

        with self.assertRaises(ValidationError):
            operations.mark_completed(self.appointment.id, actor=self.staff)

    def test_completed_appointment_cannot_be_cancelled(self):
        operations.mark_arrived(self.appointment.id, actor=self.staff)
        operations.mark_completed(self.appointment.id, actor=self.staff)

        with self.assertRaises(ValidationError):
            operations.cancel_appointment(self.appointment.id, actor=self.staff, note="Late correction.")

    def test_no_show_works_from_confirmed(self):
        operations.mark_no_show(self.appointment.id, actor=self.staff, note="Patient did not arrive.")

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.NO_SHOW)

    def test_no_show_requires_note(self):
        with self.assertRaises(ValidationError):
            operations.mark_no_show(self.appointment.id, actor=self.staff, note="")

    def test_no_show_creates_history_and_audit(self):
        operations.mark_no_show(self.appointment.id, actor=self.staff, note="Patient did not arrive.")

        self.assertTrue(
            AppointmentStatusHistory.objects.filter(
                appointment=self.appointment,
                new_status=Appointment.Status.NO_SHOW,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(self.appointment.id),
                metadata__new_status=Appointment.Status.NO_SHOW,
            ).exists()
        )

    def test_arrived_appointment_can_be_cancelled_with_note(self):
        operations.mark_arrived(self.appointment.id, actor=self.staff)
        operations.cancel_appointment(self.appointment.id, actor=self.staff, note="Administrative correction.")

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)

    def test_restore_is_intentionally_unavailable(self):
        with self.assertRaises(ValidationError):
            operations.restore_appointment(self.appointment.id, actor=self.staff)


class StaffAppointmentViewWorkflowTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff_user()
        self.client.force_login(self.staff)
        self.appointment = self.create_appointment()

    def test_staff_cancel_view_requires_note(self):
        response = self.client.post(
            reverse("staff_appointment_cancel", kwargs={"appointment_id": self.appointment.id}),
            {"note": ""},
        )

        self.assertEqual(response.status_code, 400)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CONFIRMED)

    def test_staff_cancel_view_changes_status(self):
        response = self.client.post(
            reverse("staff_appointment_cancel", kwargs={"appointment_id": self.appointment.id}),
            {"note": "Patient requested cancellation."},
        )

        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.CANCELLED)

    def test_staff_arrived_and_complete_views_change_status(self):
        arrived_response = self.client.post(
            reverse("staff_appointment_arrived", kwargs={"appointment_id": self.appointment.id}),
            {"note": "Arrived."},
        )
        complete_response = self.client.post(
            reverse("staff_appointment_complete", kwargs={"appointment_id": self.appointment.id}),
            {"note": "Completed."},
        )

        self.assertEqual(arrived_response.status_code, 302)
        self.assertEqual(complete_response.status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.COMPLETED)


class RescheduleOperationTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff_user()
        self.doctor, self.visit_type, self.tomorrow, self.first_slot = self.setup_public_booking(
            min_lead=0,
            interval=30,
        )
        self.patient = self.create_patient()
        self.appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            visit_type=self.visit_type,
            starts_at=self.first_slot.starts_at,
            ends_at=self.first_slot.ends_at,
        )
        self.second_start = self.first_slot.starts_at + timedelta(minutes=30)

    def test_staff_can_reschedule_confirmed_appointment_to_available_slot(self):
        operations.reschedule_appointment(
            self.appointment.id,
            starts_at=self.second_start,
            actor=self.staff,
            note="Patient requested a later time.",
        )

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.starts_at, self.second_start)
        self.assertEqual(self.appointment.status, Appointment.Status.RESCHEDULED)

    def test_reschedule_updates_end_time_from_visit_type_duration(self):
        operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.ends_at - self.appointment.starts_at, timedelta(minutes=30))

    def test_reschedule_creates_history_and_audit(self):
        operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

        self.assertTrue(
            AppointmentStatusHistory.objects.filter(
                appointment=self.appointment,
                old_status=Appointment.Status.CONFIRMED,
                new_status=Appointment.Status.RESCHEDULED,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(self.appointment.id),
                metadata__new_status=Appointment.Status.RESCHEDULED,
            ).exists()
        )

    def test_reschedule_rejects_occupied_slot(self):
        self.create_appointment(
            doctor=self.doctor,
            visit_type=self.visit_type,
            starts_at=self.second_start,
        )

        with self.assertRaises(ValidationError):
            operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

    def test_reschedule_rejects_closed_day(self):
        ClosedDay.objects.create(doctor=self.doctor, date=self.tomorrow, is_active=True)

        with self.assertRaises(ValidationError):
            operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

    def test_reschedule_rejects_inactive_visit_type(self):
        self.visit_type.is_active = False
        self.visit_type.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

    def test_reschedule_preserves_public_token(self):
        public_token = self.appointment.public_token

        operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.public_token, public_token)

    def test_public_success_page_still_works_after_reschedule(self):
        operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

        response = self.client.get(reverse("booking_success", kwargs={"public_token": self.appointment.public_token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.appointment.confirmation_reference)

    def test_database_integrity_error_during_reschedule_is_handled_as_validation_error(self):
        self.create_appointment(
            doctor=self.doctor,
            visit_type=self.visit_type,
            starts_at=self.second_start,
        )

        with patch("apps.booking.operations.services.is_slot_available", return_value=True), patch(
            "apps.booking.operations.services.overlaps_existing_appointment",
            return_value=False,
        ):
            with self.assertRaises(ValidationError):
                operations.reschedule_appointment(self.appointment.id, starts_at=self.second_start, actor=self.staff)

    def test_overlap_service_check_excludes_current_appointment(self):
        starts_at, ends_at = operations.validate_reschedule_target(self.appointment, self.appointment.starts_at)

        self.assertEqual(starts_at, self.appointment.starts_at)
        self.assertEqual(ends_at, self.appointment.ends_at)

    def test_active_status_uniqueness_blocks_different_active_status_same_start(self):
        patient = Patient.objects.create(
            full_name="Second Patient",
            phone_raw="0790000000",
            phone_e164="+962790000000",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                doctor=self.doctor,
                patient=patient,
                visit_type=self.visit_type,
                starts_at=self.first_slot.starts_at,
                ends_at=self.first_slot.ends_at,
                status=Appointment.Status.ARRIVED,
            )


class BookingSettingsSafetyTests(BookingTestDataMixin, TestCase):
    def test_invalid_integer_setting_falls_back_to_default(self):
        self.set_setting(SystemSetting.BOOKING_MAX_DAYS_AHEAD, "not-an-int")

        settings = services.get_booking_settings()

        self.assertEqual(settings.max_days_ahead, services.DEFAULT_BOOKING_MAX_DAYS_AHEAD)

    def test_invalid_boolean_setting_falls_back_to_default(self):
        self.set_setting(SystemSetting.BOOKING_ENABLED, "maybe", SystemSetting.ValueType.BOOLEAN)

        settings = services.get_booking_settings()

        self.assertTrue(settings.enabled)

    def test_disabled_booking_blocks_public_creation(self):
        _, visit_type, _, slot = self.setup_public_booking()
        self.set_setting(SystemSetting.BOOKING_ENABLED, False, SystemSetting.ValueType.BOOLEAN)

        with self.assertRaises(ValidationError):
            services.create_public_appointment(
                full_name="Test Patient",
                phone_raw="0791234567",
                visit_type_id=visit_type.id,
                starts_at=slot.value,
            )

    def test_invalid_booking_window_setting_does_not_crash(self):
        doctor, visit_type, tomorrow, _ = self.setup_public_booking()
        self.set_setting(SystemSetting.BOOKING_MAX_DAYS_AHEAD, "invalid")

        slots = services.generate_available_slots(visit_type, target_date=tomorrow, doctor=doctor)

        self.assertTrue(slots)

    def test_invalid_slot_interval_setting_does_not_crash(self):
        doctor, visit_type, tomorrow, _ = self.setup_public_booking()
        self.set_setting(SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES, "0")

        slots = services.generate_available_slots(visit_type, target_date=tomorrow, doctor=doctor)

        self.assertTrue(slots)

    def test_slot_interval_setting_affects_generated_slots(self):
        doctor, visit_type, tomorrow, _ = self.setup_public_booking(interval=60)

        slots = services.generate_available_slots(visit_type, target_date=tomorrow, doctor=doctor)

        self.assertEqual([slot.local_time.strftime("%H:%M") for slot in slots], ["09:00", "10:00", "11:00"])

    def test_min_lead_setting_affects_generated_slots(self):
        doctor, visit_type, tomorrow, _ = self.setup_public_booking(min_lead=0)
        self.set_setting(SystemSetting.BOOKING_MIN_LEAD_MINUTES, 60 * 24 * 7)

        slots = services.generate_available_slots(visit_type, target_date=tomorrow, doctor=doctor)

        self.assertEqual(slots, [])

    def test_max_days_ahead_setting_affects_generated_slots(self):
        doctor, visit_type, tomorrow, _ = self.setup_public_booking(max_days=1)
        far_day = tomorrow + timedelta(days=10)

        slots = services.generate_available_slots(visit_type, target_date=far_day, doctor=doctor)

        self.assertEqual(slots, [])


class PublicBookingRateLimitTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.doctor, self.visit_type, self.tomorrow, self.slot = self.setup_public_booking()
        self.post_data = {
            "full_name": "Test Patient",
            "phone": "0791234567",
            "same_as_phone": "on",
            "visit_type": str(self.visit_type.id),
            "starts_at": self.slot.value,
            "booking_note": "",
        }

    def tearDown(self):
        cache.clear()

    def test_repeated_public_booking_attempts_hit_ip_rate_limit(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 1)

        self.client.post(reverse("booking_confirm"), self.post_data, REMOTE_ADDR="10.0.0.1")
        response = self.client.post(reverse("booking_confirm"), self.post_data, REMOTE_ADDR="10.0.0.1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many booking attempts")

    def test_different_ip_has_separate_quota(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 1)
        invalid_data = dict(self.post_data, full_name="")

        self.client.post(reverse("booking_confirm"), invalid_data, REMOTE_ADDR="10.0.0.1")
        response = self.client.post(reverse("booking_confirm"), invalid_data, REMOTE_ADDR="10.0.0.2")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Too many booking attempts")

    def test_phone_quota_blocks_repeated_phone_booking(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 20)
        self.set_setting(SystemSetting.BOOKING_PHONE_RATE_LIMIT_PER_DAY, 1)
        second_data = dict(self.post_data)
        second_data["starts_at"] = (self.slot.starts_at + timedelta(minutes=30)).isoformat()

        first_response = self.client.post(reverse("booking_confirm"), self.post_data, REMOTE_ADDR="10.0.0.1")
        second_response = self.client.post(reverse("booking_confirm"), second_data, REMOTE_ADDR="10.0.0.1")

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "phone number has reached")
        self.assertEqual(Appointment.objects.count(), 1)

    def test_staff_operations_are_not_blocked_by_public_rate_limit(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 1)
        self.client.post(reverse("booking_confirm"), self.post_data, REMOTE_ADDR="10.0.0.1")
        self.client.post(reverse("booking_confirm"), self.post_data, REMOTE_ADDR="10.0.0.1")
        appointment = Appointment.objects.get()
        staff = self.create_staff_user()
        self.client.force_login(staff)

        response = self.client.post(
            reverse("staff_appointment_cancel", kwargs={"appointment_id": appointment.id}),
            {"note": "Patient called."},
            REMOTE_ADDR="10.0.0.1",
        )

        self.assertEqual(response.status_code, 302)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)


class StaffQueryBehaviorTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff_user()
        self.client.force_login(self.staff)
        self.doctor = self.create_doctor()
        self.visit_type = self.create_visit_type(doctor=self.doctor)
        for index in range(5):
            self.create_appointment(
                doctor=self.doctor,
                visit_type=self.visit_type,
                starts_at=self.future_aware(days=index + 1, hour=9),
            )

    def test_staff_appointment_list_avoids_obvious_n_plus_one_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("staff_appointment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 15)

    def test_staff_detail_uses_select_related_for_related_objects(self):
        appointment = Appointment.objects.first()

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("staff_appointment_detail", kwargs={"appointment_id": appointment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 15)

    def test_public_booking_visit_type_list_does_not_create_appointments(self):
        response = self.client.get(reverse("booking_visit_type"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 5)

    def test_public_slot_generation_does_not_query_per_slot_for_single_day(self):
        tomorrow = timezone.localdate() + timedelta(days=20)
        self.create_schedule(self.doctor, weekday=tomorrow.weekday(), start=time(9, 0), end=time(12, 0))
        settings = services.BookingSettings(True, 0, 30, 15, 180)

        with CaptureQueriesContext(connection) as queries:
            slots = services.generate_available_slots(
                self.visit_type,
                target_date=tomorrow,
                settings=settings,
                doctor=self.doctor,
            )

        self.assertTrue(slots)
        self.assertLessEqual(len(queries), 4)


class PublicPrivacyBoundaryTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.doctor, self.visit_type, self.tomorrow, self.slot = self.setup_public_booking()
        self.appointment = services.create_public_appointment(
            full_name="Test Patient",
            phone_raw="0791234567",
            visit_type_id=self.visit_type.id,
            starts_at=self.slot.value,
            booking_note="Private transport note.",
        )

    def test_public_success_page_uses_token_url(self):
        response = self.client.get(reverse("booking_success", kwargs={"public_token": self.appointment.public_token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.appointment.confirmation_reference)

    def test_numeric_success_url_returns_404(self):
        response = self.client.get(f"/book/success/{self.appointment.id}/")

        self.assertEqual(response.status_code, 404)

    def test_public_success_page_does_not_show_audit_entries_or_internal_notes(self):
        operations.cancel_appointment(self.appointment.id, actor=self.create_staff_user(), note="Staff-only reason.")
        response = self.client.get(reverse("booking_success", kwargs={"public_token": self.appointment.public_token}))

        self.assertNotContains(response, "Audit events")
        self.assertNotContains(response, "operation_note")
        self.assertNotContains(response, "Staff-only reason")
        self.assertNotContains(response, "Private transport note")
        self.assertNotContains(response, "Internal ID")

    def test_public_booking_forms_do_not_expose_staff_urls(self):
        response = self.client.get(
            reverse("booking_confirm"),
            {"visit_type": self.visit_type.id, "starts_at": (self.slot.starts_at + timedelta(minutes=30)).isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/staff/appointments/")

    def test_no_patient_portal_route_exists(self):
        response = self.client.get("/portal/")

        self.assertEqual(response.status_code, 404)

    def test_no_upload_route_exists(self):
        response = self.client.get("/uploads/")

        self.assertEqual(response.status_code, 404)

    def test_no_whatsapp_api_or_webhook_route_exists(self):
        webhook_response = self.client.get("/whatsapp/webhook/")
        api_response = self.client.get("/api/whatsapp/")

        self.assertEqual(webhook_response.status_code, 404)
        self.assertEqual(api_response.status_code, 404)
