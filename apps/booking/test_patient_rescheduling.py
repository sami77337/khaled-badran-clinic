from datetime import timedelta
import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, connection
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.booking import operations, rescheduling
from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.booking.tests import BookingTestDataMixin
from apps.clinic.models import ClosedDay
from apps.core.models import AuditLog, SystemSetting
from apps.patients.models import Patient


class RescheduleFixtureMixin(BookingTestDataMixin):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.doctor = self.create_doctor()
        self.visit_type = self.create_visit_type(doctor=self.doctor)
        self.patient = self.create_patient()
        self.target = self.future_aware(days=2, hour=10)
        self.create_schedule(self.doctor, weekday=self.target.weekday())
        self.appointment = self.create_appointment(
            doctor=self.doctor, visit_type=self.visit_type, patient=self.patient,
            starts_at=timezone.now() - timedelta(days=2), status=Appointment.Status.NO_SHOW,
        )
        self.appointment.reminder_sent_at = timezone.now() - timedelta(days=3)
        self.appointment.booking_note = "Private booking note"
        self.appointment.contact_phone_raw = "0791234567"
        self.appointment.contact_phone_e164 = "+962791234567"
        self.appointment.whatsapp_phone_raw = "0799999999"
        self.appointment.whatsapp_phone_e164 = "+962799999999"
        self.appointment.save()
        self.prior_history = AppointmentStatusHistory.objects.create(
            appointment=self.appointment, old_status=Appointment.Status.CONFIRMED,
            new_status=Appointment.Status.NO_SHOW, note="Private previous no-show evidence",
        )
        self.token = rescheduling.make_reschedule_token(self.appointment)

    def url(self, route="patient_reschedule", token=None, language="ar"):
        return reverse(route + ("_en" if language == "en" else ""), kwargs={"token": token or self.token})

    def post(self, **extra):
        return self.client.post(self.url("patient_reschedule_confirm"), {
            "starts_at": self.target.isoformat(), **extra,
        })

    def snapshot(self):
        return {
            "appointments": list(Appointment.objects.order_by("pk").values()),
            "patients": list(Patient.objects.order_by("pk").values()),
            "history": list(AppointmentStatusHistory.objects.order_by("pk").values()),
            "audit": list(AuditLog.objects.order_by("pk").values()),
        }

    def assert_private_failure(self, response, *, status=400):
        self.assertEqual(response.status_code, status)
        for private in (
            self.patient.full_name, self.patient.phone_e164, self.appointment.booking_note,
            self.appointment.confirmation_reference, self.prior_history.note,
            self.visit_type.name_en, self.visit_type.name_ar,
        ):
            self.assertNotContains(response, private, status_code=status)


class PatientReschedulingTests(RescheduleFixtureMixin, TestCase):
    def test_anonymous_access_reuses_slots_without_patient_details_fields(self):
        for language, direction in (("ar", "rtl"), ("en", "ltr")):
            with self.subTest(language=language):
                response = self.client.get(self.url(language=language))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "booking/select_slot.html")
                self.assertContains(response, f'dir="{direction}"')
                self.assertContains(response, self.appointment.confirmation_reference)
                self.assertContains(response, "data-booking-slot-step")
                for field in ("full_name", "phone", "doctor", "visit_type"):
                    self.assertNotContains(response, f'name="{field}"')
                self.assertNotContains(response, self.patient.full_name)
                self.assertNotContains(response, self.patient.phone_e164)
                self.assertNotContains(response, self.appointment.booking_note)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertEqual(response["Referrer-Policy"], "no-referrer")
                self.assertIn("noindex", response["X-Robots-Tag"])

    def test_tampered_expired_wrong_purpose_and_malformed_tokens_fail_closed(self):
        payload = signing.loads(self.token, salt=rescheduling.RESCHEDULE_SALT)
        variants = [
            self.token[:-1] + ("a" if self.token[-1] != "a" else "b"),
            str(self.appointment.public_token), self.patient.phone_e164,
            signing.dumps(payload, salt="another-purpose"),
            signing.dumps({"appointment": "not-a-uuid"}, salt=rescheduling.RESCHEDULE_SALT),
            signing.dumps([], salt=rescheduling.RESCHEDULE_SALT),
        ]
        with patch("django.core.signing.time.time", return_value=1):
            variants.append(rescheduling.make_reschedule_token(self.appointment))
        before = self.snapshot()
        for token in variants:
            with self.subTest(token=token[:12]):
                for route in ("patient_reschedule", "patient_reschedule_confirm", "patient_reschedule_success"):
                    self.assert_private_failure(self.client.get(self.url(route, token)))
                self.assert_private_failure(self.client.post(self.url("patient_reschedule_confirm", token), {
                    "starts_at": self.target.isoformat(),
                }))
        self.assertEqual(self.snapshot(), before)

    def test_no_phone_only_lookup_and_cannot_switch_target(self):
        other = self.create_appointment(
            doctor=self.doctor, visit_type=self.visit_type, patient=self.patient,
            starts_at=timezone.now() - timedelta(days=4), status=Appointment.Status.NO_SHOW,
        )
        other_before = Appointment.objects.filter(pk=other.pk).values().get()
        with CaptureQueriesContext(connection) as queries:
            self.assert_private_failure(self.client.post(self.url("patient_reschedule_confirm", "phone-only"), {
                "phone": self.patient.phone_e164, "starts_at": self.target.isoformat(),
            }))
        self.assertFalse(any('FROM "booking_appointment"' in item["sql"] for item in queries))
        response = self.post(appointment_id=other.pk, public_token=other.public_token, phone=self.patient.phone_e164)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Appointment.objects.filter(pk=other.pk).values().get(), other_before)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.RESCHEDULED)

    def test_only_exact_current_no_show_and_staff_rules_unchanged(self):
        for status in Appointment.Status.values:
            if status == Appointment.Status.NO_SHOW:
                continue
            with self.subTest(status=status):
                Appointment.objects.filter(pk=self.appointment.pk).update(status=status)
                self.assert_private_failure(self.client.get(self.url()))
                self.assert_private_failure(self.post())
        self.assertNotIn(Appointment.Status.NO_SHOW, operations.RESCHEDULE_ALLOWED_FROM)
        self.assertIn(Appointment.Status.NO_SHOW, operations.TERMINAL_STATUSES)
        for status in operations.TERMINAL_STATUSES:
            Appointment.objects.filter(pk=self.appointment.pk).update(status=status)
            with self.assertRaises(ValidationError):
                operations.reschedule_appointment(self.appointment.pk, starts_at=self.target)

    def test_no_show_history_alone_does_not_authorize_link(self):
        self.appointment.status = Appointment.Status.CONFIRMED
        self.appointment.save()
        with self.assertRaises(ValidationError):
            rescheduling.make_reschedule_token(self.appointment)
        self.assert_private_failure(self.post())

    def test_success_preserves_row_identity_details_and_no_show_history_resets_reminder(self):
        before = self.snapshot()
        response = self.post(note="untrusted patient input", full_name="Changed", phone="000", visit_type="999", doctor="999")
        self.assertEqual(response.status_code, 302)
        self.appointment.refresh_from_db()
        after = Appointment.objects.values().get(pk=self.appointment.pk)
        expected = before["appointments"][0]
        for key in expected:
            if key not in {"starts_at", "ends_at", "status", "reminder_sent_at", "updated_at"}:
                self.assertEqual(after[key], expected[key], key)
        self.assertEqual(after["starts_at"], self.target)
        self.assertEqual(after["ends_at"], self.target + timedelta(minutes=self.visit_type.duration_minutes))
        self.assertEqual(after["status"], Appointment.Status.RESCHEDULED)
        self.assertIsNone(after["reminder_sent_at"])
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(list(Patient.objects.values()), before["patients"])
        self.assertIsNone(self.appointment.patient.user_id)
        self.assertEqual(AppointmentStatusHistory.objects.filter(pk=self.prior_history.pk).values().get(), before["history"][0])
        history = self.appointment.status_history.exclude(pk=self.prior_history.pk).get()
        self.assertEqual((history.old_status, history.new_status), (Appointment.Status.NO_SHOW, Appointment.Status.RESCHEDULED))
        self.assertIsNone(history.changed_by)
        self.assertEqual(history.note, rescheduling.SELF_SERVICE_NOTE)
        audit = AuditLog.objects.get(object_id=str(self.appointment.pk), model_name="Appointment")
        self.assertEqual(audit.message, rescheduling.SELF_SERVICE_NOTE)
        self.assertEqual(audit.action, AuditLog.Action.STATUS_CHANGE)
        self.assertEqual(audit.metadata["old_status"], Appointment.Status.NO_SHOW)
        self.assertEqual(audit.metadata["new_status"], Appointment.Status.RESCHEDULED)
        self.assertIn("old_starts_at", audit.metadata)
        self.assertIn("new_starts_at", audit.metadata)
        for secret in (self.token, self.patient.phone_e164, self.patient.full_name, "untrusted patient input"):
            self.assertNotIn(secret, str(audit.metadata) + audit.object_repr + audit.message)
        success = self.client.get(response.url)
        self.assertContains(success, "تمت إعادة جدولة موعدك")
        self.assertContains(success, self.target.strftime("%H:%M"))
        self.assert_private_failure(self.post())
        self.assertEqual(AppointmentStatusHistory.objects.count(), 2)

    def test_linked_account_sees_same_appointment_and_unrelated_login_is_not_attributed(self):
        owner = get_user_model().objects.create_user(username="reschedule-owner")
        unrelated = get_user_model().objects.create_user(username="unrelated-browser-user")
        self.patient.user = owner
        self.patient.save()
        self.client.force_login(unrelated)
        self.assertEqual(self.post().status_code, 302)
        self.assertIsNone(self.appointment.status_history.first().changed_by)
        self.client.force_login(owner)
        response = self.client.get(reverse("patient_portal_appointment_list"))
        items = response.context["appointments"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].appointment.pk, self.appointment.pk)
        self.assertEqual(items[0].appointment.public_token, self.appointment.public_token)
        self.assertEqual(items[0].appointment.starts_at, self.target)
        self.assertEqual(items[0].appointment.status, Appointment.Status.RESCHEDULED)

    def test_get_never_mutates_including_selected_slot_confirm_success_and_errors(self):
        before = self.snapshot()
        for route in ("patient_reschedule", "patient_reschedule_confirm", "patient_reschedule_success"):
            self.client.get(self.url(route), {"starts_at": self.target.isoformat(), "confirm": "1"})
        self.client.get(self.url(token="bad"))
        self.assertEqual(self.snapshot(), before)
        success_url = self.post().url
        after = self.snapshot()
        self.client.get(success_url)
        self.client.get(success_url)
        self.assertEqual(self.snapshot(), after)

    def test_csrf_protected_post_and_no_mutating_other_methods(self):
        client = Client(enforce_csrf_checks=True)
        confirm_url = self.url("patient_reschedule_confirm")
        before = self.snapshot()
        self.assertEqual(client.post(confirm_url, {"starts_at": self.target.isoformat()}).status_code, 403)
        self.assertEqual(client.get(confirm_url, {"starts_at": self.target.isoformat()}).status_code, 200)
        for method in ("put", "patch", "delete"):
            self.assertEqual(getattr(client, method)(confirm_url, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code, 405)
        self.assertEqual(client.post(self.url()).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        response = client.post(confirm_url, {
            "starts_at": self.target.isoformat(), "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        })
        self.assertEqual(response.status_code, 302)

    def test_english_confirmation_success_and_receipt_is_read_only(self):
        response = self.client.get(self.url("patient_reschedule_confirm", language="en"), {"starts_at": self.target.isoformat()})
        self.assertContains(response, "Confirm Reschedule")
        self.assertContains(response, 'dir="ltr"')
        self.assertEqual(response.context["slot_display"], self.target)
        response = self.client.post(self.url("patient_reschedule_confirm", language="en"), {"starts_at": self.target.isoformat()})
        success = self.client.get(response.url)
        self.assertContains(success, "Your Appointment Was Rescheduled")
        self.assertContains(success, 'dir="ltr"')
        receipt = response.url.split("/")[-3]
        self.assert_private_failure(self.client.get(self.url(token=receipt)))
        self.assertEqual(self.client.post(response.url).status_code, 405)
        with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + rescheduling.RECEIPT_MAX_AGE + 5):
            self.assert_private_failure(self.client.get(response.url))

    def test_old_token_cannot_revive_on_a_later_no_show(self):
        self.assertEqual(self.post().status_code, 302)
        self.appointment.refresh_from_db()
        self.appointment.status = Appointment.Status.NO_SHOW
        self.appointment.save()
        self.assert_private_failure(self.client.get(self.url()))
        fresh = rescheduling.make_reschedule_token(self.appointment)
        self.assertEqual(self.client.get(self.url(token=fresh)).status_code, 200)

    def test_unrelated_update_revokes_token(self):
        self.appointment.save()
        self.assert_private_failure(self.post())

    def test_exact_collision_and_partial_overlap_and_stale_slot_fail_without_data(self):
        self.assertEqual(self.client.get(self.url("patient_reschedule_confirm"), {"starts_at": self.target.isoformat()}).status_code, 200)
        for delta in (0, 15, -15):
            with self.subTest(delta=delta):
                blocker = self.create_appointment(
                    doctor=self.doctor, patient=self.patient, visit_type=self.visit_type,
                    starts_at=self.target + timedelta(minutes=delta),
                )
                before = self.snapshot()
                self.assert_private_failure(self.post())
                self.assertEqual(self.snapshot(), before)
                blocker.delete()

    def test_shared_availability_rules_are_enforced(self):
        for key, value in (
            (SystemSetting.BOOKING_ENABLED, "false"),
            (SystemSetting.BOOKING_MIN_LEAD_MINUTES, "10000"),
            (SystemSetting.BOOKING_MAX_DAYS_AHEAD, "1"),
        ):
            with self.subTest(key=key):
                setting = SystemSetting.objects.create(key=key, value=value)
                self.assert_private_failure(self.post())
                setting.delete()
        closure = ClosedDay.objects.create(date=self.target.date(), doctor=self.doctor)
        self.assert_private_failure(self.post())
        closure.delete()
        for obj in (self.doctor, self.visit_type):
            obj.is_active = False
            obj.save()
            self.assert_private_failure(self.post())
            obj.is_active = True
            obj.save()
        for invalid in ("", "not-a-date", "2026-99-99T10:00", (self.target + timedelta(minutes=1)).isoformat(),
                        self.target.replace(hour=23).isoformat(), (self.target - timedelta(days=5)).isoformat()):
            with self.subTest(invalid=invalid):
                cache.clear()
                self.assert_private_failure(self.post(starts_at=invalid))
        self.assertEqual(Appointment.objects.count(), 1)

    def test_special_hours_override_and_global_closed_day_are_reused(self):
        from datetime import time
        self.create_schedule_override(self.doctor, self.target.date(), start=time(14), end=time(16))
        self.assert_private_failure(self.post())
        self.target = self.target.replace(hour=14)
        self.assertEqual(self.client.get(self.url("patient_reschedule_confirm"), {"starts_at": self.target.isoformat()}).status_code, 200)
        ClosedDay.objects.create(date=self.target.date())
        self.assert_private_failure(self.post())

    def test_constraint_race_and_database_contention_roll_back(self):
        before = self.snapshot()
        for error in (IntegrityError("synthetic collision"), OperationalError("synthetic contention")):
            with self.subTest(error=type(error).__name__), patch.object(Appointment, "save", side_effect=error):
                self.assert_private_failure(self.post())
            self.assertEqual(self.snapshot(), before)

    def test_audit_failure_rolls_back_appointment_and_history(self):
        before = self.snapshot()
        with patch("apps.booking.operations.create_appointment_audit", side_effect=IntegrityError("synthetic audit failure")):
            self.assert_private_failure(self.post())
        self.assertEqual(self.snapshot(), before)

    def test_token_payload_contains_no_patient_contact_or_internal_identifiers(self):
        payload = signing.loads(self.token, salt=rescheduling.RESCHEDULE_SALT)
        self.assertEqual(set(payload), {"appointment", "version"})
        self.assertIsInstance(payload["version"], str)
        self.assertEqual(payload["appointment"], str(self.appointment.public_token))
        self.assertNotIn(self.patient.phone_e164, str(payload))
        self.assertNotIn(self.patient.full_name, str(payload))

    def test_post_rate_limit_fails_without_appointment_data(self):
        SystemSetting.objects.create(key=SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR, value="1")
        self.assert_private_failure(self.post(starts_at="bad"))
        before = self.snapshot()
        self.assert_private_failure(self.post(), status=429)
        self.assertEqual(self.snapshot(), before)

    def test_must_select_a_new_slot_and_visit_type_must_exist(self):
        self.appointment.starts_at = self.target
        self.appointment.ends_at = self.target + timedelta(minutes=30)
        self.appointment.save()
        self.token = rescheduling.make_reschedule_token(self.appointment)
        response = self.client.get(self.url(), {"starts_at": self.target.isoformat()})
        self.assertIsNone(response.context["selected_slot"])
        self.assert_private_failure(self.client.get(self.url("patient_reschedule_confirm"), {
            "starts_at": self.target.isoformat(),
        }))
        self.assert_private_failure(self.post())
        self.appointment.visit_type = None
        self.appointment.save()
        self.token = rescheduling.make_reschedule_token(self.appointment)
        self.assert_private_failure(self.post())

    def test_reschedule_links_are_redacted_from_application_logs(self):
        from apps.booking.logging import RescheduleLinkPrivacyFilter

        for language in ("ar", "en"):
            path = self.url("patient_reschedule_confirm", language=language)
            record = logging.LogRecord("django.request", logging.WARNING, "", 0, "Bad Request: %s", (path,), None)
            record.request = RequestFactory().get(path)
            record.exc_text = "sensitive traceback"
            self.assertTrue(RescheduleLinkPrivacyFilter().filter(record))
            self.assertNotIn(self.token, record.getMessage())
            self.assertIn("[redacted]/confirm/", record.getMessage())
            self.assertIsNone(record.request)
            self.assertIsNone(record.exc_text)

    def test_read_contention_also_fails_without_patient_context(self):
        before = self.snapshot()
        with patch("apps.booking.rescheduling.resolve_reschedule_token", side_effect=OperationalError("synthetic read lock")):
            for route in ("patient_reschedule", "patient_reschedule_confirm", "patient_reschedule_success"):
                self.assert_private_failure(self.client.get(self.url(route)))
            self.assert_private_failure(self.post())
        self.assertEqual(self.snapshot(), before)
