from datetime import datetime, time, timedelta
from io import StringIO
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.booking.countries import INTERNATIONAL_PHONE_COUNTRIES
from apps.booking.forms import PUBLIC_BOOKING_ERROR_COPY, PublicBookingForm
from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.booking.phone import normalize_phone
from apps.booking import operations, rate_limits, services
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

    def test_public_field_and_validation_contract_is_stable(self):
        expected_fields = (
            "full_name",
            "phone",
            "same_as_phone",
            "whatsapp_phone",
            "visit_type",
            "starts_at",
            "booking_note",
        )
        expected_required = {
            "full_name": True,
            "phone": True,
            "same_as_phone": False,
            "whatsapp_phone": False,
            "visit_type": True,
            "starts_at": True,
            "booking_note": False,
        }

        for language in ("ar", "en"):
            with self.subTest(language=language):
                form = PublicBookingForm(language=language)

                self.assertEqual(tuple(form.fields), expected_fields)
                self.assertEqual(
                    {name: field.required for name, field in form.fields.items()},
                    expected_required,
                )
                self.assertEqual(form.fields["full_name"].max_length, 255)
                self.assertEqual(form.fields["phone"].max_length, 50)
                self.assertEqual(form.fields["whatsapp_phone"].max_length, 50)
                self.assertTrue(form.fields["visit_type"].widget.is_hidden)
                self.assertTrue(form.fields["starts_at"].widget.is_hidden)
                self.assertEqual(form.fields["same_as_phone"].widget.input_type, "checkbox")
                self.assertEqual(form.fields["booking_note"].widget.__class__.__name__, "Textarea")
                self.assertIsNone(form.fields["booking_note"].max_length)

    def test_valid_form_validates_normalized_phone(self):
        form = PublicBookingForm(data=self.valid_form_data())

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.normalized_phone, "+962791234567")

    def test_checked_same_as_phone_copies_primary_phone(self):
        data = self.valid_form_data()
        data["whatsapp_phone"] = "+442071234567"

        form = PublicBookingForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.normalized_phone, "+962791234567")
        self.assertEqual(form.normalized_whatsapp_phone, "+962791234567")
        self.assertEqual(form.cleaned_data["whatsapp_phone"], "0791234567")

    def test_unchecked_same_as_phone_keeps_valid_separate_whatsapp(self):
        data = self.valid_form_data()
        data.pop("same_as_phone")
        data["whatsapp_phone"] = "+442071234567"

        form = PublicBookingForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.normalized_phone, "+962791234567")
        self.assertEqual(form.normalized_whatsapp_phone, "+442071234567")
        self.assertEqual(form.cleaned_data["whatsapp_phone"], "+442071234567")

    def test_blank_whatsapp_falls_back_to_primary_phone(self):
        data = self.valid_form_data()
        data.pop("same_as_phone")
        data["whatsapp_phone"] = ""

        form = PublicBookingForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.normalized_whatsapp_phone, "+962791234567")
        self.assertEqual(form.cleaned_data["whatsapp_phone"], "0791234567")

    def test_invalid_separate_whatsapp_keeps_localized_field_error(self):
        for language in ("ar", "en"):
            with self.subTest(language=language):
                data = self.valid_form_data()
                data.pop("same_as_phone")
                data["whatsapp_phone"] = "not-a-phone"

                form = PublicBookingForm(data=data, language=language)

                self.assertFalse(form.is_valid())
                self.assertIn("whatsapp_phone", form.errors)
                self.assertIn(
                    PUBLIC_BOOKING_ERROR_COPY[language]["phone_invalid"],
                    str(form.errors["whatsapp_phone"]),
                )

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
        self.assertIn(PUBLIC_BOOKING_ERROR_COPY["ar"]["slot_unavailable"], str(form.errors))

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

    def test_note_preserves_content_and_trims_only_outer_whitespace(self):
        data = self.valid_form_data()
        data["booking_note"] = "  Please call after 3 PM.\nUse the side entrance.  "

        form = PublicBookingForm(data=data)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["booking_note"],
            "Please call after 3 PM.\nUse the side entrance.",
        )


class PublicBookingViewTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        self.doctor, self.visit_type, self.tomorrow, self.slot = self.setup_public_booking()

    def test_book_home_returns_200(self):
        response = self.client.get(reverse("book"))

        self.assertEqual(response.status_code, 200)

    def test_english_book_home_returns_200(self):
        response = self.client.get(reverse("book_en"))

        self.assertEqual(response.status_code, 200)

    def test_public_booking_routes_do_not_require_login(self):
        route_requests = [
            (reverse("book"), {}),
            (reverse("book_en"), {}),
            (reverse("booking_visit_type"), {}),
            (reverse("booking_visit_type_en"), {}),
            (
                reverse("booking_slots"),
                {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
            ),
            (
                reverse("booking_slots_en"),
                {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
            ),
            (
                reverse("booking_confirm"),
                {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
            ),
            (
                reverse("booking_confirm_en"),
                {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
            ),
        ]

        for url, params in route_requests:
            with self.subTest(url=url):
                response = self.client.get(url, params)

                self.assertEqual(response.status_code, 200)
                self.assertNotIn("/portal/login/", response.request.get("PATH_INFO", ""))

    def test_public_booking_flow_uses_public_shell_without_mobile_booking_cta(self):
        route_requests = [
            (reverse("book"), {}),
            (reverse("book_en"), {}),
            (reverse("booking_visit_type"), {}),
            (reverse("booking_visit_type_en"), {}),
            (
                reverse("booking_slots"),
                {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
            ),
            (
                reverse("booking_slots_en"),
                {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
            ),
            (
                reverse("booking_confirm"),
                {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
            ),
            (
                reverse("booking_confirm_en"),
                {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
            ),
        ]

        for url, params in route_requests:
            with self.subTest(url=url):
                response = self.client.get(url, params)

                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "data-mobile-booking-cta")
                self.assertContains(response, "/static/css/public.css")
                self.assertContains(response, '<footer class="site-footer">')

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
        self.assertEqual(appointment.booking_note, "Please call before appointment.")

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
        self.assertContains(response, PUBLIC_BOOKING_ERROR_COPY["ar"]["slot_unavailable"])

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

    def test_closed_day_is_excluded_from_public_date_selector(self):
        ClosedDay.objects.create(doctor=self.doctor, date=self.tomorrow, is_active=True)

        response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.tomorrow, [group["date"] for group in response.context["grouped_slots"]])
        self.assertNotEqual(response.context["selected_date"], self.tomorrow)
        self.assertNotContains(response, f'data-booking-date="{self.tomorrow.isoformat()}"')
        self.assertContains(response, "data-booking-slot")

    def test_min_lead_time_excludes_near_date_and_selects_next_available_date(self):
        self.set_setting(SystemSetting.BOOKING_MIN_LEAD_MINUTES, 60 * 24 * 7)

        response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.context["selected_date"], self.tomorrow)
        self.assertNotContains(response, f'data-booking-date="{self.tomorrow.isoformat()}"')
        self.assertContains(response, "data-booking-slot")

    def test_out_of_range_requested_date_falls_back_to_first_available_date(self):
        far_day = timezone.localdate() + timedelta(days=60)

        response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id, "date": far_day.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_date"], self.tomorrow)
        self.assertNotContains(response, f'data-booking-date="{far_day.isoformat()}"')
        self.assertContains(response, "data-booking-slot")

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

    def test_patient_portal_is_authenticated_and_upload_route_is_absent(self):
        portal_response = self.client.get("/portal/")
        uploads_response = self.client.get("/uploads/")

        self.assertEqual(portal_response.status_code, 302)
        self.assertIn(reverse("patient_portal_login"), portal_response["Location"])
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


class PublicBookingVisualContractTests(BookingTestDataMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.doctor, self.visit_type, self.tomorrow, self.slot = self.setup_public_booking()

    def tearDown(self):
        cache.clear()

    def assert_bounded_booking_shell(self, response, *, direction):
        self.assertEqual(response.status_code, 200)
        page_title = "احجز موعدك" if direction == "rtl" else "Book Your Appointment"
        self.assertContains(response, f'dir="{direction}"')
        self.assertContains(response, f"<title>{page_title}</title>", html=True)
        self.assertEqual(response.context["page_title"], page_title)
        self.assertContains(response, "/static/css/booking.css")
        self.assertContains(response, "/static/css/public.css")
        self.assertContains(response, "data-booking-flow")
        self.assertContains(response, "data-booking-card")
        self.assertContains(response, '<footer class="site-footer">')
        self.assertContains(
            response,
            (
                f'<a class="btn btn-light" href="{response.context["contact_url"]}">'
                f'{response.context["labels"]["contact"]}</a>'
            ),
            html=True,
        )
        self.assertEqual(response.context["footer_primary_url"], response.context["contact_url"])
        self.assertEqual(response.context["footer_primary_label"], response.context["labels"]["contact"])
        self.assertNotContains(response, "data-mobile-booking-cta")
        self.assertNotContains(response, 'type="file"')

    def assert_booking_language_switch(self, response, *, route_name, query):
        switch_url = urlsplit(response.context["language_switch"]["url"])
        self.assertEqual(switch_url.path, reverse(route_name))
        self.assertEqual(parse_qs(switch_url.query), {key: [str(value)] for key, value in query.items()})

    def test_visit_type_step_uses_figma_booking_contract_in_arabic_and_english(self):
        additional_visit_types = []
        for index in range(1, 6):
            additional_visit_types.append(
                VisitType.objects.create(
                    doctor=self.doctor,
                    name_ar=f"زيارة إضافية {index}",
                    name_en=f"Additional visit {index}",
                    duration_minutes=30 + index * 5,
                    display_order=index,
                    is_active=True,
                )
            )
        inactive_visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="خدمة غير متاحة",
            name_en="Unavailable service",
            duration_minutes=60,
            display_order=7,
            is_active=False,
        )
        selected_additional_type = additional_visit_types[3]
        route_cases = [
            (
                "booking_visit_type",
                "booking_slots",
                "rtl",
                "احجز موعدك",
                "اختر الخدمة",
                self.visit_type.name_ar,
                "عرض المزيد",
                "عرض أقل",
            ),
            (
                "booking_visit_type_en",
                "booking_slots_en",
                "ltr",
                "Book Your Appointment",
                "Select a Service",
                self.visit_type.name_en,
                "Show more",
                "Show less",
            ),
        ]

        for route_name, slots_route, direction, heading, card_heading, visit_name, show_more, show_less in route_cases:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assert_bounded_booking_shell(response, direction=direction)
                self.assertContains(response, "data-booking-progress")
                self.assertContains(response, "data-booking-service-step", count=1)
                self.assertContains(response, "/static/js/booking.js", count=1)
                self.assertContains(response, "data-booking-visit-option", count=6)
                self.assertContains(response, '<a class="booking-visit-option"', count=6)
                self.assertContains(response, "data-booking-primary-services", count=1)
                self.assertContains(response, "data-booking-additional-services", count=1)
                self.assertContains(response, "data-booking-service-more", count=1)
                self.assertNotContains(response, "data-booking-service-more open")
                self.assertEqual(len(response.context["primary_visit_types"]), 4)
                self.assertEqual(len(response.context["remaining_visit_types"]), 2)
                self.assertContains(response, heading)
                self.assertContains(response, card_heading)
                self.assertContains(response, visit_name)
                self.assertContains(response, show_more)
                self.assertContains(response, show_less)
                self.assertNotContains(
                    response,
                    inactive_visit_type.name_ar if direction == "rtl" else inactive_visit_type.name_en,
                )
                self.assertContains(response, "data-booking-continue", count=1)
                self.assertContains(response, 'aria-disabled="true"', count=1)
                if direction == "rtl":
                    self.assertContains(response, f"{self.visit_type.duration_minutes} دقيقة")
                    self.assertNotContains(response, "تقريبًا")
                else:
                    self.assertContains(response, f"{self.visit_type.duration_minutes} min")
                    self.assertNotContains(response, "Approx.")
                self.assertContains(
                    response,
                    f'href="{reverse(route_name)}?visit_type={self.visit_type.id}"',
                )

                selected_response = self.client.get(
                    reverse(route_name),
                    {"visit_type": selected_additional_type.id},
                )
                self.assertContains(
                    selected_response,
                    'class="booking-visit-option is-selected"',
                    count=1,
                )
                self.assertContains(selected_response, 'aria-current="true"', count=1)
                self.assertNotContains(selected_response, 'aria-disabled="true"')
                self.assertContains(selected_response, "data-booking-service-more open", count=1)
                self.assertTrue(selected_response.context["visit_types_expanded"])
                self.assertContains(
                    selected_response,
                    f'href="{reverse(slots_route)}?visit_type={selected_additional_type.id}"',
                )
                self.assertContains(
                    selected_response,
                    "متابعة" if direction == "rtl" else "Continue",
                )
                self.assert_booking_language_switch(
                    selected_response,
                    route_name="booking_visit_type_en" if direction == "rtl" else "booking_visit_type",
                    query={"visit_type": selected_additional_type.id},
                )
                self.assertEqual(Appointment.objects.count(), 0)
                self.assertEqual(Patient.objects.count(), 0)

                inactive_response = self.client.get(
                    reverse(route_name),
                    {"visit_type": inactive_visit_type.id},
                )
                self.assertNotContains(inactive_response, 'class="booking-visit-option is-selected"')
                self.assertContains(inactive_response, 'aria-disabled="true"', count=1)
                self.assertNotContains(
                    inactive_response,
                    inactive_visit_type.name_ar if direction == "rtl" else inactive_visit_type.name_en,
                )

    def test_progress_indicator_has_three_localized_figma_steps_and_server_backed_states(self):
        language_cases = [
            ("", ("الخدمة", "التاريخ والوقت", "التفاصيل")),
            ("_en", ("Service", "Date &amp; Time", "Details")),
        ]
        step_cases = [
            ("booking_visit_type", {}, 0),
            (
                "booking_slots",
                {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
                1,
            ),
            (
                "booking_confirm",
                {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
                2,
            ),
        ]

        for route_suffix, labels in language_cases:
            for route_name, query, completed_count in step_cases:
                localized_route_name = f"{route_name}{route_suffix}"
                with self.subTest(route_name=localized_route_name):
                    response = self.client.get(reverse(localized_route_name), query)

                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "data-booking-progress")
                    self.assertContains(response, '<li class="booking-step', count=3)
                    self.assertContains(response, 'class="booking-step is-active"', count=1)
                    self.assertContains(
                        response,
                        'class="booking-step is-complete"',
                        count=completed_count,
                    )
                    self.assertContains(response, 'aria-current="step"', count=1)
                    for label in labels:
                        self.assertContains(response, label, html=True)

    def test_visit_type_rows_exclude_price_and_instruction_hierarchy(self):
        self.visit_type.price = "73.25"
        self.visit_type.show_price_to_patient = True
        self.visit_type.instructions_ar = "تعليمات عربية معتمدة من قاعدة البيانات"
        self.visit_type.instructions_en = "Approved English database instructions"
        self.visit_type.save(
            update_fields=[
                "price",
                "show_price_to_patient",
                "instructions_ar",
                "instructions_en",
            ]
        )
        hidden_price_visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="خدمة بسعر مخفي",
            name_en="Hidden-price service",
            duration_minutes=20,
            price="987.65",
            show_price_to_patient=False,
            is_active=True,
        )
        route_cases = [
            (
                "booking_visit_type",
                self.visit_type.instructions_ar,
                self.visit_type.instructions_en,
                hidden_price_visit_type.name_ar,
                "73,25",
                "987,65",
            ),
            (
                "booking_visit_type_en",
                self.visit_type.instructions_en,
                self.visit_type.instructions_ar,
                hidden_price_visit_type.name_en,
                "73.25",
                "987.65",
            ),
        ]

        for (
            route_name,
            visible_instruction,
            other_language_instruction,
            hidden_visit_name,
            localized_visible_price,
            localized_hidden_price,
        ) in route_cases:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertNotContains(response, visible_instruction)
                self.assertNotContains(response, other_language_instruction)
                self.assertNotContains(response, localized_visible_price)
                self.assertContains(response, hidden_visit_name)
                self.assertNotContains(response, localized_hidden_price)
                self.assertContains(response, f"{self.visit_type.duration_minutes}")

    def test_slot_step_uses_real_backend_slots_in_arabic_and_english(self):
        route_cases = [
            (
                "booking_slots",
                "booking_visit_type",
                "booking_slots_en",
                "booking_confirm",
                "rtl",
                "اختر التاريخ والوقت",
                "رجوع",
                self.visit_type.name_ar,
            ),
            (
                "booking_slots_en",
                "booking_visit_type_en",
                "booking_slots",
                "booking_confirm_en",
                "ltr",
                "Select Date &amp; Time",
                "Back",
                self.visit_type.name_en,
            ),
        ]

        for (
            route_name,
            visit_type_route,
            alternate_slot_route,
            confirm_route,
            direction,
            heading,
            back_label,
            visit_name,
        ) in route_cases:
            with self.subTest(route_name=route_name):
                response = self.client.get(
                    reverse(route_name),
                    {"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
                )

                self.assert_bounded_booking_shell(response, direction=direction)
                self.assertContains(response, "data-booking-progress")
                self.assertContains(response, "data-booking-back", count=1)
                self.assertContains(response, back_label)
                self.assertContains(response, "data-booking-selected-service")
                self.assertContains(response, 'class="booking-selection-summary is-selected"')
                self.assertContains(response, visit_name)
                self.assertContains(
                    response,
                    f'href="{reverse(visit_type_route)}?visit_type={self.visit_type.id}"',
                    count=1,
                )
                if direction == "rtl":
                    self.assertContains(response, f"{self.visit_type.duration_minutes} دقيقة")
                else:
                    self.assertContains(response, f"{self.visit_type.duration_minutes} min")
                self.assertContains(response, "data-booking-date-groups", count=1)
                self.assertContains(response, "data-booking-slot-step", count=1)
                self.assertContains(response, "/static/js/booking.js", count=1)
                self.assertContains(response, "data-booking-selected-date", count=1)
                self.assertContains(response, "data-booking-slot")
                self.assertContains(response, "data-booking-slot-continue", count=1)
                self.assertContains(response, 'aria-disabled="true"', count=1)
                self.assertNotContains(response, f'href="{reverse(confirm_route)}')
                self.assertContains(response, heading, html=True)
                self.assertContains(response, self.slot.local_time.strftime("%H:%M"))
                self.assert_booking_language_switch(
                    response,
                    route_name=alternate_slot_route,
                    query={"visit_type": self.visit_type.id, "date": self.tomorrow.isoformat()},
                )

                selected_response = self.client.get(
                    reverse(route_name),
                    {
                        "visit_type": self.visit_type.id,
                        "date": self.tomorrow.isoformat(),
                        "starts_at": self.slot.value,
                    },
                )
                self.assertEqual(selected_response.context["selected_slot"].value, self.slot.value)
                self.assertContains(
                    selected_response,
                    'class="booking-date-button is-selected"',
                    count=1,
                )
                self.assertContains(
                    selected_response,
                    'class="booking-slot-button is-selected"',
                    count=1,
                )
                self.assertContains(selected_response, "data-booking-selected-date", count=1)
                self.assertContains(selected_response, "data-booking-selected-time", count=1)
                self.assertContains(selected_response, 'aria-current="date"', count=1)
                self.assertContains(selected_response, 'aria-current="time"', count=1)
                self.assertNotContains(selected_response, 'aria-disabled="true"')
                self.assertContains(
                    selected_response,
                    f'href="{reverse(confirm_route)}?visit_type={self.visit_type.id}',
                    count=1,
                )
                self.assert_booking_language_switch(
                    selected_response,
                    route_name=alternate_slot_route,
                    query={
                        "visit_type": self.visit_type.id,
                        "date": self.tomorrow.isoformat(),
                        "starts_at": self.slot.value,
                    },
                )
                self.assertEqual(Appointment.objects.count(), 0)
                self.assertEqual(Patient.objects.count(), 0)

                invalid_response = self.client.get(
                    reverse(route_name),
                    {
                        "visit_type": self.visit_type.id,
                        "date": self.tomorrow.isoformat(),
                        "starts_at": "not-a-real-slot",
                    },
                )
                self.assertIsNone(invalid_response.context["selected_slot"])
                self.assertNotContains(invalid_response, "data-booking-selected-time")
                self.assertContains(invalid_response, 'aria-disabled="true"', count=1)
                self.assertNotContains(invalid_response, f'href="{reverse(confirm_route)}')

    def test_slot_step_tracks_the_current_server_provided_availability(self):
        replacement_slot = services.BookingSlot(
            starts_at=self.slot.starts_at + timedelta(minutes=30),
            ends_at=self.slot.ends_at + timedelta(minutes=30),
        )
        route_cases = [
            ("booking_slots", "booking_confirm"),
            ("booking_slots_en", "booking_confirm_en"),
        ]

        for route_name, confirm_route in route_cases:
            with self.subTest(route_name=route_name):
                query = {
                    "visit_type": self.visit_type.id,
                    "date": self.tomorrow.isoformat(),
                    "starts_at": self.slot.value,
                }
                with patch(
                    "apps.booking.views.services.generate_available_slots",
                    return_value=[self.slot],
                ) as generate_slots:
                    available_response = self.client.get(reverse(route_name), query)

                generate_slots.assert_called_once_with(
                    visit_type=self.visit_type,
                    target_date=None,
                    doctor=self.doctor,
                )
                self.assertEqual(available_response.context["selected_slot"], self.slot)
                self.assertContains(available_response, "data-booking-selected-time", count=1)
                self.assertContains(
                    available_response,
                    f'href="{reverse(confirm_route)}?visit_type={self.visit_type.id}',
                    count=1,
                )

                with patch(
                    "apps.booking.views.services.generate_available_slots",
                    return_value=[replacement_slot],
                ):
                    changed_response = self.client.get(reverse(route_name), query)

                self.assertIsNone(changed_response.context["selected_slot"])
                self.assertNotContains(changed_response, "data-booking-selected-time")
                self.assertNotContains(changed_response, self.slot.local_time.strftime("%H:%M"))
                self.assertContains(
                    changed_response,
                    replacement_slot.local_time.strftime("%H:%M"),
                )
                self.assertContains(changed_response, 'aria-disabled="true"', count=1)
                self.assertNotContains(changed_response, f'href="{reverse(confirm_route)}')

    def test_patient_details_surface_keeps_final_server_post_as_creation_boundary(self):
        route_cases = [
            ("booking_confirm", "booking_slots", "rtl", "بيانات المريض", "تعديل"),
            ("booking_confirm_en", "booking_slots_en", "ltr", "Patient Details", "Edit"),
        ]

        for route_name, slots_route, direction, heading, edit_label in route_cases:
            with self.subTest(route_name=route_name):
                response = self.client.get(
                    reverse(route_name),
                    {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
                )

                self.assert_bounded_booking_shell(response, direction=direction)
                self.assertContains(response, "data-booking-review")
                self.assertContains(response, "data-booking-appointment-summary", count=1)
                self.assertContains(response, "data-booking-back", count=1)
                self.assertContains(response, "data-booking-edit", count=1)
                self.assertContains(response, edit_label)
                edit_url = f"{reverse(slots_route)}?{urlencode({
                    'visit_type': self.visit_type.id,
                    'date': self.tomorrow.isoformat(),
                    'starts_at': self.slot.value,
                })}"
                self.assertContains(response, edit_url.replace("&", "&amp;"), count=2)
                edit_response = self.client.get(edit_url)
                self.assertEqual(edit_response.status_code, 200)
                self.assertEqual(edit_response.context["selected_slot"].value, self.slot.value)
                self.assertContains(edit_response, "data-booking-selected-time", count=1)
                self.assertContains(response, heading)
                self.assertContains(response, 'method="post"')
                self.assertContains(response, 'name="csrfmiddlewaretoken"')
                self.assertEqual(response.context["starts_at"], self.slot.value)
                self.assertEqual(str(response.context["form"]["visit_type"].value()), str(self.visit_type.id))
                self.assert_booking_language_switch(
                    response,
                    route_name="booking_confirm_en" if direction == "rtl" else "booking_confirm",
                    query={"visit_type": self.visit_type.id, "starts_at": self.slot.value},
                )
                self.assertEqual(Appointment.objects.count(), 0)
                self.assertEqual(Patient.objects.count(), 0)

        template_source = (
            Path(__file__).resolve().parents[2] / "templates" / "booking" / "confirm.html"
        ).read_text(encoding="utf-8")
        for removed_copy in (
            "Secure direct booking",
            "Review Booking Details",
            "Appointment summary",
            "Secure direct details",
            "doctor.display_name_",
            "clinic.address_",
        ):
            with self.subTest(removed_copy=removed_copy):
                self.assertNotIn(removed_copy, template_source)

    def test_patient_detail_fields_keep_django_contract_and_figma_states(self):
        route_cases = [
            (
                "booking_confirm",
                "بيانات المريض",
                PUBLIC_BOOKING_ERROR_COPY["ar"]["full_name_required"],
                PUBLIC_BOOKING_ERROR_COPY["ar"]["phone_required"],
            ),
            (
                "booking_confirm_en",
                "Patient Details",
                PUBLIC_BOOKING_ERROR_COPY["en"]["full_name_required"],
                PUBLIC_BOOKING_ERROR_COPY["en"]["phone_required"],
            ),
        ]

        for route_name, heading, full_name_error, phone_error in route_cases:
            with self.subTest(route_name=route_name):
                route = reverse(route_name)
                query = {"visit_type": self.visit_type.id, "starts_at": self.slot.value}
                response = self.client.get(route, query)

                self.assertContains(response, "data-booking-patient-details", count=1)
                self.assertContains(response, "data-booking-patient-form", count=1)
                self.assertContains(response, "data-booking-field", count=5)
                self.assertContains(response, 'class="booking-control"', count=3)
                self.assertContains(response, 'class="booking-control booking-textarea"', count=1)
                self.assertContains(response, 'class="booking-checkbox"', count=1)
                self.assertContains(response, heading)
                self.assertContains(response, "/static/js/booking.js")
                self.assertContains(response, 'autocomplete="name"', count=1)
                self.assertContains(response, 'autocomplete="tel"', count=2)
                self.assertContains(response, 'inputmode="tel"', count=2)
                self.assertContains(response, 'name="phone"', count=1)
                self.assertContains(response, 'name="whatsapp_phone"', count=1)
                self.assertContains(response, 'name="same_as_phone"', count=1)
                self.assertContains(response, 'name="visit_type"', count=1)
                self.assertContains(response, 'name="starts_at"', count=1)
                self.assertContains(response, "data-booking-phone-control", count=2)
                self.assertContains(response, "data-booking-country-trigger", count=2)
                self.assertContains(response, "data-booking-country-search", count=2)
                self.assertContains(
                    response,
                    "data-booking-country-option\n",
                    count=len(INTERNATIONAL_PHONE_COUNTRIES) * 2,
                )
                self.assertContains(response, 'data-booking-default-dial-code="+962"', count=2)
                self.assertContains(response, 'placeholder="79XXXXXXX"', count=2)
                self.assertNotContains(response, "+962…")
                self.assertNotContains(response, "or +962")
                self.assertNotContains(response, "أو +962")
                self.assertContains(response, 'data-country-code="JO"', count=2)
                self.assertContains(response, 'data-country-example="79XXXXXXX"', count=2)
                self.assertContains(response, 'data-country-example="5XXXXXXXX"', count=4)
                for dial_code in (
                    "+962",
                    "+966",
                    "+971",
                    "+974",
                    "+965",
                    "+968",
                    "+973",
                    "+964",
                    "+970",
                    "+20",
                    "+961",
                    "+1",
                    "+44",
                ):
                    self.assertContains(
                        response,
                        f'data-country-dial="{dial_code}"',
                        count=(
                            sum(
                                country["dial_code"] == dial_code
                                for country in INTERNATIONAL_PHONE_COUNTRIES
                            )
                            * 2
                        ),
                    )
                if route_name == "booking_confirm":
                    self.assertContains(response, "الأردن")
                    self.assertContains(response, "المملكة المتحدة")
                    self.assertContains(response, "ابحث عن دولة أو رمز")
                else:
                    self.assertContains(response, "Jordan")
                    self.assertContains(response, "United Kingdom")
                    self.assertContains(response, "Search country or code")

                invalid_response = self.client.post(
                    route,
                    {
                        "visit_type": self.visit_type.id,
                        "starts_at": self.slot.value,
                        "full_name": "",
                        "phone": "",
                        "same_as_phone": "on",
                        "whatsapp_phone": "",
                        "booking_note": "",
                    },
                )

                self.assertEqual(invalid_response.status_code, 200)
                self.assertContains(invalid_response, 'class="form-field has-error"', count=2)
                self.assertContains(invalid_response, 'aria-invalid="true"', count=2)
                self.assertContains(invalid_response, "booking-field-errors", count=2)
                self.assertContains(invalid_response, full_name_error)
                self.assertContains(invalid_response, phone_error)
                self.assertEqual(Appointment.objects.count(), 0)
                self.assertEqual(Patient.objects.count(), 0)

        script_source = (
            Path(__file__).resolve().parents[2] / "static" / "js" / "booking.js"
        ).read_text(encoding="utf-8")
        for contract_hook in (
            "data-booking-service-step",
            "data-booking-slot-step",
            "event.preventDefault()",
            "window.history.replaceState",
            "preserveViewport",
            "setActionState",
            "[name='same_as_phone']",
            "[name='whatsapp_phone']",
            "bookingComposeNumber",
            'form.addEventListener("formdata"',
            "event.formData.set(input.name, control.bookingComposeNumber())",
            "bookingDialCode",
            "bookingNationalPrefix",
            "stripDomesticPrefix",
            "number.slice(matchingCountry.dataset.countryDial.length)",
            "whatsappField.hidden = isSame",
        ):
            with self.subTest(contract_hook=contract_hook):
                self.assertIn(contract_hook, script_source)
        self.assertNotIn("input.value = `${selectedDial}", script_source)

        phone_field_template = (
            Path(__file__).resolve().parents[2]
            / "templates"
            / "booking"
            / "partials"
            / "international_phone_field.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Formatting example", phone_field_template)
        self.assertIn("مثال للتنسيق", phone_field_template)
        self.assertNotIn("valid format", phone_field_template.lower())
        self.assertNotIn("تنسيق صالح", phone_field_template)

    def test_international_phone_metadata_is_expanded_local_and_jordan_first(self):
        self.assertGreaterEqual(len(INTERNATIONAL_PHONE_COUNTRIES), 240)
        self.assertEqual(INTERNATIONAL_PHONE_COUNTRIES[0]["code"], "JO")
        self.assertEqual(INTERNATIONAL_PHONE_COUNTRIES[0]["dial_code"], "+962")
        self.assertEqual(INTERNATIONAL_PHONE_COUNTRIES[0]["example"], "79XXXXXXX")
        self.assertEqual(INTERNATIONAL_PHONE_COUNTRIES[0]["national_prefix"], "0")

        countries_by_code = {
            country["code"]: country for country in INTERNATIONAL_PHONE_COUNTRIES
        }
        self.assertEqual(len(countries_by_code), len(INTERNATIONAL_PHONE_COUNTRIES))
        self.assertEqual(countries_by_code["SA"]["example"], "5XXXXXXXX")
        self.assertEqual(countries_by_code["SA"]["national_prefix"], "0")
        self.assertEqual(countries_by_code["AE"]["example"], "5XXXXXXXX")
        self.assertEqual(countries_by_code["AE"]["national_prefix"], "0")
        self.assertEqual(countries_by_code["GB"]["example"], "7XXX XXXXXX")
        self.assertEqual(countries_by_code["GB"]["national_prefix"], "0")
        self.assertEqual(countries_by_code["US"]["national_prefix"], "1")
        for country in INTERNATIONAL_PHONE_COUNTRIES:
            with self.subTest(country_code=country["code"]):
                self.assertTrue(country["flag"])
                self.assertTrue(country["name_ar"])
                self.assertTrue(country["name_en"])
                self.assertTrue(country["dial_code"].startswith("+"))
                self.assertTrue(country["example"])
                self.assertFalse(country["example"].startswith("+"))
                compact_example = "".join(
                    character
                    for character in country["example"]
                    if character not in " -()./"
                )
                if country["national_prefix"]:
                    self.assertFalse(
                        compact_example.startswith(country["national_prefix"]),
                        msg=f'{country["code"]} example still contains its domestic prefix',
                    )

    def test_booking_internal_warning_boxes_are_removed_but_global_policy_remains(self):
        templates_root = Path(__file__).resolve().parents[2] / "templates" / "booking"
        booking_template_source = "\n".join(
            (templates_root / template_name).read_text(encoding="utf-8")
            for template_name in ("confirm.html", "success.html", "unavailable.html")
        )
        for removed_fragment in (
            "booking-submit-note",
            "booking-success-notice",
            "labels.not_emergency",
            "For privacy, this page does not display",
            "حفاظًا على الخصوصية، لا تعرض هذه الصفحة",
        ):
            with self.subTest(removed_fragment=removed_fragment):
                self.assertNotIn(removed_fragment, booking_template_source)

        confirm_response = self.client.get(
            reverse("booking_confirm"),
            {"visit_type": self.visit_type.id, "starts_at": self.slot.value},
        )
        self.assertNotContains(confirm_response, 'class="booking-submit-note"')
        self.assertContains(confirm_response, 'class="footer-emergency"', count=1)

    def test_same_step_controls_keep_server_fallbacks_and_load_no_reload_hooks(self):
        visit_type_response = self.client.get(reverse("booking_visit_type"))
        self.assertContains(visit_type_response, "data-booking-service-step", count=1)
        self.assertContains(visit_type_response, "/static/js/booking.js", count=1)
        self.assertContains(
            visit_type_response,
            f'href="{reverse("booking_visit_type")}?visit_type={self.visit_type.id}"',
            count=1,
        )
        service_template_source = (
            Path(__file__).resolve().parents[2] / "templates" / "booking" / "select_visit_type.html"
        ).read_text(encoding="utf-8")
        self.assertIn("data-booking-service-more", service_template_source)

        slot_response = self.client.get(
            reverse("booking_slots"),
            {"visit_type": self.visit_type.id},
        )
        self.assertContains(slot_response, "data-booking-slot-step", count=1)
        self.assertContains(slot_response, "/static/js/booking.js", count=1)
        for group in slot_response.context["grouped_slots"]:
            fallback = (
                f'{reverse("booking_slots")}?visit_type={self.visit_type.id}'
                f'&amp;date={group["date"].isoformat()}'
            )
            self.assertContains(slot_response, f'href="{fallback}"', count=1)
            for slot in group["slots"]:
                self.assertContains(
                    slot_response,
                    urlencode({"starts_at": slot.value}),
                    count=1,
                )

        script_source = (
            Path(__file__).resolve().parents[2] / "static" / "js" / "booking.js"
        ).read_text(encoding="utf-8")
        for hook in (
            'option.addEventListener("click"',
            'button.addEventListener("click"',
            'slot.addEventListener("click"',
            'moreToggle?.addEventListener("click"',
            "event.preventDefault()",
            "window.history.replaceState",
            "window.scrollTo(left, top)",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, script_source)

    def test_available_dates_switch_one_real_server_backed_time_group(self):
        for route_name in ("booking_slots", "booking_slots_en"):
            with self.subTest(route_name=route_name):
                response = self.client.get(
                    reverse(route_name),
                    {"visit_type": self.visit_type.id},
                )
                grouped_slots = response.context["grouped_slots"]

                self.assertGreater(len(grouped_slots), 1)
                self.assertContains(response, "data-booking-date-groups", count=1)
                self.assertContains(
                    response,
                    " data-booking-date-group ",
                    count=len(grouped_slots),
                )
                self.assertContains(
                    response,
                    "data-booking-time-grid",
                    count=len(grouped_slots),
                )
                self.assertContains(
                    response,
                    " data-booking-slot data-booking-slot-value=",
                    count=sum(len(group["slots"]) for group in grouped_slots),
                )
                self.assertEqual(response.context["selected_date"], grouped_slots[0]["date"])
                self.assertEqual(response.context["selected_date_slots"], grouped_slots[0]["slots"])
                for group in grouped_slots:
                    date_value = group["date"].strftime("%Y-%m-%d")
                    self.assertContains(response, f'data-booking-date="{date_value}"')

                requested_group = grouped_slots[1]
                requested_response = self.client.get(
                    reverse(route_name),
                    {
                        "visit_type": self.visit_type.id,
                        "date": requested_group["date"].isoformat(),
                    },
                )
                self.assertEqual(requested_response.context["selected_date"], requested_group["date"])
                self.assertEqual(
                    requested_response.context["selected_date_slots"],
                    requested_group["slots"],
                )
                self.assertContains(
                    requested_response,
                    "data-booking-time-grid",
                    count=len(grouped_slots),
                )
                self.assertContains(
                    requested_response,
                    " data-booking-slot data-booking-slot-value=",
                    count=sum(len(group["slots"]) for group in grouped_slots),
                )
                self.assertContains(
                    requested_response,
                    f'data-booking-date="{requested_group["date"].isoformat()}" data-booking-selected-date',
                    count=1,
                )

    def test_empty_and_unavailable_states_use_the_localized_booking_treatment(self):
        slot_cases = [
            ("booking_slots", "rtl", "لا توجد أوقات متاحة"),
            ("booking_slots_en", "ltr", "No available times"),
        ]
        for route_name, direction, empty_heading in slot_cases:
            with self.subTest(route_name=route_name):
                with patch(
                    "apps.booking.views.services.generate_available_slots",
                    return_value=[],
                ):
                    response = self.client.get(
                        reverse(route_name),
                        {"visit_type": self.visit_type.id},
                    )

                self.assert_bounded_booking_shell(response, direction=direction)
                self.assertContains(response, 'class="booking-empty-state"', count=1)
                self.assertContains(response, empty_heading)
                self.assertNotContains(response, " data-booking-slot data-booking-slot-value=")

        self.set_setting(SystemSetting.BOOKING_ENABLED, False, SystemSetting.ValueType.BOOLEAN)
        unavailable_cases = [
            ("book", "rtl", "الحجز غير متاح حاليًا"),
            ("book_en", "ltr", "Booking unavailable"),
        ]
        for route_name, direction, unavailable_heading in unavailable_cases:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assert_bounded_booking_shell(response, direction=direction)
                self.assertContains(response, 'class="booking-unavailable-panel"', count=1)
                self.assertContains(response, unavailable_heading)

    def test_arabic_and_english_routes_show_localized_inline_errors(self):
        invalid_data = {
            "full_name": "",
            "phone": "12345",
            "visit_type": str(self.visit_type.id),
            "starts_at": self.slot.value,
            "booking_note": "",
        }

        arabic_response = self.client.post(
            reverse("booking_confirm"),
            invalid_data,
            REMOTE_ADDR="10.10.0.1",
        )
        english_response = self.client.post(
            reverse("booking_confirm_en"),
            invalid_data,
            REMOTE_ADDR="10.10.0.2",
        )

        self.assertContains(arabic_response, PUBLIC_BOOKING_ERROR_COPY["ar"]["full_name_required"])
        self.assertContains(arabic_response, PUBLIC_BOOKING_ERROR_COPY["ar"]["phone_invalid"])
        self.assertNotContains(arabic_response, PUBLIC_BOOKING_ERROR_COPY["en"]["full_name_required"])
        self.assertContains(english_response, PUBLIC_BOOKING_ERROR_COPY["en"]["full_name_required"])
        self.assertContains(english_response, PUBLIC_BOOKING_ERROR_COPY["en"]["phone_invalid"])
        self.assertNotContains(english_response, PUBLIC_BOOKING_ERROR_COPY["ar"]["full_name_required"])
        self.assertEqual(Appointment.objects.count(), 0)

    def test_success_uses_real_appointment_data_without_public_patient_pii(self):
        appointment = services.create_public_appointment(
            full_name="Visual Privacy Patient",
            phone_raw="0798765432",
            visit_type_id=self.visit_type.id,
            starts_at=self.slot.value,
            booking_note="PRIVATE VISUAL CONTRACT NOTE",
        )
        route_cases = [
            ("booking_success", "rtl", self.doctor.display_name_ar, self.visit_type.name_ar, "مجمع الفيحاء الطبي"),
            (
                "booking_success_en",
                "ltr",
                self.doctor.display_name_en,
                self.visit_type.name_en,
                "Al Fayhaa Medical Complex",
            ),
        ]

        for route_name, direction, doctor_name, visit_name, location in route_cases:
            with self.subTest(route_name=route_name):
                response = self.client.get(
                    reverse(route_name, kwargs={"public_token": appointment.public_token})
                )

                self.assert_bounded_booking_shell(response, direction=direction)
                self.assertContains(response, "data-booking-success")
                self.assertContains(response, appointment.confirmation_reference)
                self.assertContains(response, doctor_name)
                self.assertContains(response, visit_name)
                self.assertContains(response, location)
                self.assertContains(response, "https://wa.me/962789766332")
                if direction == "rtl":
                    self.assertContains(response, "،")
                else:
                    self.assertNotContains(response, "،")
                self.assertNotContains(response, "Visual Privacy Patient")
                self.assertNotContains(response, "0798765432")
                self.assertNotContains(response, "PRIVATE VISUAL CONTRACT NOTE")
                self.assertNotContains(response, "#KB-9X28")
                self.assertNotContains(response, "Add to calendar")
                self.assertNotContains(response, "إضافة للتقويم")
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_booking_styles_cover_required_responsive_layout_contract(self):
        stylesheet_path = finders.find("css/booking.css")

        self.assertIsNotNone(stylesheet_path)
        stylesheet = Path(stylesheet_path).read_text(encoding="utf-8")
        required_rules = [
            "width: min(calc(100% - 2rem), 48rem)",
            "grid-template-columns: repeat(2, minmax(0, 1fr))",
            "grid-template-columns: repeat(3, minmax(0, 1fr))",
            ".page-booking .booking-visit-option",
            "min-height: 5.25rem",
            "border-radius: 0.5rem",
            ".page-booking .booking-visit-option:hover",
            ".page-booking .booking-visit-option.is-selected",
            ".page-booking .booking-visit-more",
            ".page-booking .booking-visit-more[open]",
            ".page-booking .booking-continue-action",
            ".page-booking .booking-selection-marker",
            ".page-booking .booking-selection-duration",
            ".page-booking .booking-date-list",
            ".page-booking .booking-date-button.is-selected",
            ".page-booking .booking-slot-grid",
            ".page-booking .booking-slot-button.is-selected",
            ".page-booking .booking-appointment-summary",
            ".page-booking .booking-summary-edit",
            ".page-booking .booking-form .booking-control",
            ".page-booking .booking-form .booking-control::placeholder",
            ".page-booking .booking-form .has-error .booking-control",
            ".page-booking .booking-form .booking-checkbox",
            ".page-booking .booking-phone-control",
            ".page-booking .booking-country-trigger",
            ".page-booking .booking-country-menu",
            "width: min(20rem, 100%)",
            "max-height: 15rem",
            ".page-booking .booking-field-errors .errorlist",
            "font-variant-numeric: tabular-nums",
            "white-space: nowrap",
            "unicode-bidi: plaintext",
            "font-synthesis: none",
            "text-rendering: optimizeLegibility",
            'font-family: "IBM Plex Sans Arabic"',
            'font-family: "Noto Kufi Arabic"',
            "@media (max-width: 389px)",
            "@media (min-width: 600px)",
            "@media (min-width: 900px)",
            "margin-inline",
            "inset-inline-start",
            "overflow-x: clip",
        ]
        for rule in required_rules:
            with self.subTest(rule=rule):
                self.assertIn(rule, stylesheet)
        self.assertNotIn("grid-template-columns: repeat(4, minmax(0, 1fr))", stylesheet)
        self.assertNotIn("position: fixed", stylesheet)


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

    def test_appointment_model_declares_expected_slot_constraints(self):
        constraint_names = {constraint.name for constraint in Appointment._meta.constraints}

        self.assertIn("appointment_ends_after_start", constraint_names)
        self.assertIn("unique_appointment_doctor_start_status", constraint_names)
        self.assertIn("unique_active_appointment_doctor_start", constraint_names)

    def test_slot_collision_logic_treats_active_statuses_as_blocking(self):
        doctor = self.create_doctor()
        visit_type = self.create_visit_type(doctor=doctor)
        starts_at = self.future_aware(days=3, hour=9)
        active_statuses = [
            Appointment.Status.CONFIRMED,
            Appointment.Status.ARRIVED,
            Appointment.Status.RESCHEDULED,
        ]

        for index, status in enumerate(active_statuses):
            with self.subTest(status=status):
                Appointment.objects.all().delete()
                appointment_start = starts_at + timedelta(days=index)
                self.create_appointment(
                    doctor=doctor,
                    visit_type=visit_type,
                    starts_at=appointment_start,
                    status=status,
                )

                self.assertTrue(
                    services.overlaps_existing_appointment(
                        doctor,
                        appointment_start,
                        appointment_start + timedelta(minutes=visit_type.duration_minutes),
                    )
                )

    def test_slot_collision_logic_ignores_terminal_statuses(self):
        doctor = self.create_doctor()
        visit_type = self.create_visit_type(doctor=doctor)
        starts_at = self.future_aware(days=3, hour=10)
        terminal_statuses = [
            Appointment.Status.COMPLETED,
            Appointment.Status.CANCELLED,
            Appointment.Status.NO_SHOW,
        ]

        for index, status in enumerate(terminal_statuses):
            with self.subTest(status=status):
                Appointment.objects.all().delete()
                appointment_start = starts_at + timedelta(days=index)
                self.create_appointment(
                    doctor=doctor,
                    visit_type=visit_type,
                    starts_at=appointment_start,
                    status=status,
                )

                self.assertFalse(
                    services.overlaps_existing_appointment(
                        doctor,
                        appointment_start,
                        appointment_start + timedelta(minutes=visit_type.duration_minutes),
                    )
                )


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


class SeedBookingDemoCommandTests(TestCase):
    def test_seed_booking_demo_does_not_create_patient_or_appointment_records(self):
        output = StringIO()

        call_command("seed_booking_demo", stdout=output)

        text = output.getvalue()
        self.assertIn("Seeded booking demo setup", text)
        self.assertIn("No patients, appointments", text)
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(Appointment.objects.count(), 0)


class BookingClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, *, remote_addr="10.0.0.10", forwarded_for=None):
        extra = {"REMOTE_ADDR": remote_addr}
        if forwarded_for is not None:
            extra["HTTP_X_FORWARDED_FOR"] = forwarded_for
        return self.factory.get("/", **extra)

    def test_get_client_ip_ignores_forwarded_for_by_default(self):
        request = self.request(remote_addr="10.0.0.10", forwarded_for="203.0.113.5, 198.51.100.7")

        self.assertEqual(rate_limits.get_client_ip(request), "10.0.0.10")

    @override_settings(BOOKING_TRUST_X_FORWARDED_FOR=True)
    def test_get_client_ip_uses_first_forwarded_for_ip_when_trusted(self):
        request = self.request(remote_addr="10.0.0.10", forwarded_for="203.0.113.5, 198.51.100.7")

        self.assertEqual(rate_limits.get_client_ip(request), "203.0.113.5")

    @override_settings(BOOKING_TRUST_X_FORWARDED_FOR=True)
    def test_get_client_ip_falls_back_to_remote_addr_when_trusted_header_missing(self):
        request = self.request(remote_addr="10.0.0.10")

        self.assertEqual(rate_limits.get_client_ip(request), "10.0.0.10")


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
        self.assertContains(response, PUBLIC_BOOKING_ERROR_COPY["ar"]["too_many_attempts"])

    def test_different_ip_has_separate_quota(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 1)
        invalid_data = dict(self.post_data, full_name="")

        self.client.post(reverse("booking_confirm"), invalid_data, REMOTE_ADDR="10.0.0.1")
        response = self.client.post(reverse("booking_confirm"), invalid_data, REMOTE_ADDR="10.0.0.2")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, PUBLIC_BOOKING_ERROR_COPY["ar"]["too_many_attempts"])

    @override_settings(BOOKING_TRUST_X_FORWARDED_FOR=False)
    def test_forwarded_for_changes_do_not_bypass_ip_rate_limit_when_untrusted(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 1)
        invalid_data = dict(self.post_data, full_name="")

        self.client.post(
            reverse("booking_confirm"),
            invalid_data,
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.1",
        )
        response = self.client.post(
            reverse("booking_confirm"),
            invalid_data,
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.2",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, PUBLIC_BOOKING_ERROR_COPY["ar"]["too_many_attempts"])

    @override_settings(BOOKING_TRUST_X_FORWARDED_FOR=True)
    def test_forwarded_for_ips_have_separate_rate_limit_when_trusted(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 1)
        invalid_data = dict(self.post_data, full_name="")

        self.client.post(
            reverse("booking_confirm"),
            invalid_data,
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.1",
        )
        second_response = self.client.post(
            reverse("booking_confirm"),
            invalid_data,
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.2",
        )
        third_response = self.client.post(
            reverse("booking_confirm"),
            invalid_data,
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.1",
        )

        self.assertEqual(second_response.status_code, 200)
        self.assertNotContains(second_response, PUBLIC_BOOKING_ERROR_COPY["ar"]["too_many_attempts"])
        self.assertEqual(third_response.status_code, 200)
        self.assertContains(third_response, PUBLIC_BOOKING_ERROR_COPY["ar"]["too_many_attempts"])

    def test_phone_quota_blocks_repeated_phone_booking(self):
        self.set_setting(SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, 20)
        self.set_setting(SystemSetting.BOOKING_PHONE_RATE_LIMIT_PER_DAY, 1)
        second_data = dict(self.post_data)
        second_data["starts_at"] = (self.slot.starts_at + timedelta(minutes=30)).isoformat()

        first_response = self.client.post(reverse("booking_confirm"), self.post_data, REMOTE_ADDR="10.0.0.1")
        second_response = self.client.post(reverse("booking_confirm"), second_data, REMOTE_ADDR="10.0.0.1")

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, PUBLIC_BOOKING_ERROR_COPY["ar"]["phone_limit"])
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

    def test_booking_rate_limit_cache_keys_hash_sensitive_identities(self):
        observed_keys = []
        original_add = rate_limits.cache.add
        request = RequestFactory().post("/", REMOTE_ADDR="203.0.113.99")

        def capture_key(key, *args, **kwargs):
            observed_keys.append(key)
            return original_add(key, *args, **kwargs)

        with patch("apps.booking.rate_limits.cache.add", side_effect=capture_key):
            rate_limits.check_public_booking_ip_rate_limit(request)
            rate_limits.check_public_booking_phone_rate_limit("+962791234567")

        self.assertTrue(observed_keys)
        for key in observed_keys:
            with self.subTest(key=key):
                self.assertIn("booking-rate:", key)
                self.assertNotIn("203.0.113.99", key)
                self.assertNotIn("0791234567", key)
                self.assertNotIn("+962791234567", key)


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

    def test_public_success_page_offers_optional_portal_link(self):
        response = self.client.get(reverse("booking_success", kwargs={"public_token": self.appointment.public_token}))

        self.assertContains(response, reverse("patient_portal_link_appointment"))
        self.assertContains(response, str(self.appointment.public_token))

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

    def test_patient_portal_route_requires_authentication(self):
        response = self.client.get("/portal/")

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("patient_portal_login"), response["Location"])

    def test_patient_medical_records_route_requires_authentication(self):
        response = self.client.get("/portal/medical-records/")

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("patient_portal_login"), response["Location"])

    def test_no_upload_route_exists(self):
        response = self.client.get("/uploads/")

        self.assertEqual(response.status_code, 404)

    def test_no_upload_unscoped_medical_record_whatsapp_or_payment_routes_exist(self):
        blocked_paths = [
            "/uploads/",
            "/portal/uploads/",
            "/whatsapp/webhook/",
            "/api/whatsapp/",
            "/whatsapp/api/",
            "/records/",
            "/medical-records/",
            "/payments/",
            "/portal/payments/",
        ]

        for path in blocked_paths:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 404)
