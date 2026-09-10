from datetime import timedelta
from io import StringIO
import json
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.db import connection, transaction
from django.db.backends.postgresql.base import DatabaseWrapper
from django.db.models.sql.compiler import SQLCompiler
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.booking.forms import PublicBookingForm
from apps.booking.models import Appointment
from apps.booking.services import create_public_appointment
from apps.clinic.models import Doctor, VisitType
from apps.patients.models import Patient
from . import booking
from .test_meta import META_SETTINGS, SYNTHETIC_PHONE


@override_settings(**META_SETTINGS)
class WhatsAppBookingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.doctor = Doctor.objects.create(
            full_name_ar="Synthetic", full_name_en="Synthetic"
        )
        self.patient = Patient.objects.create(
            full_name="Synthetic", phone_e164=SYNTHETIC_PHONE
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="Synthetic",
            name_en="Synthetic",
            duration_minutes=30,
        )
        self.now = timezone.now()
        self.http = patch("apps.whatsapp.meta.http.client.HTTPSConnection").start()
        self.addCleanup(patch.stopall)
        response = self.http.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = b'{"messages":[{"id":"synthetic-message-id"}]}'

    def appointment(self, **changes):
        offset = timedelta(minutes=Appointment.objects.count())
        starts_at = self.now + timedelta(hours=1) + offset
        return Appointment.objects.create(
            **{
                "doctor": self.doctor,
                "patient": self.patient,
                "visit_type": self.visit_type,
                "starts_at": starts_at,
                "ends_at": starts_at + timedelta(minutes=30),
                "booking_note": "private-payload-sentinel",
                "whatsapp_phone_e164": SYNTHETIC_PHONE,
                **changes,
            }
        )

    def test_due_eligibility_respects_offset_status_activity_and_previous_send(self):
        due = self.appointment()
        rescheduled = self.appointment(status=Appointment.Status.RESCHEDULED)
        for status in (
            Appointment.Status.CANCELLED,
            Appointment.Status.COMPLETED,
            Appointment.Status.NO_SHOW,
            Appointment.Status.ARRIVED,
        ):
            self.appointment(status=status)
        self.appointment(reminder_enabled=False)
        self.appointment(reminder_sent_at=self.now)
        self.appointment(reminder_offset=timedelta(minutes=15))
        self.appointment(starts_at=self.now - timedelta(minutes=10))
        self.appointment(
            starts_at=self.now + timedelta(days=2),
            ends_at=self.now + timedelta(days=2, minutes=30),
        )
        self.assertEqual(
            set(booking.due_reminders(self.now).values_list("pk", flat=True)),
            {due.pk, rescheduled.pk},
        )

    def test_success_marks_sent_after_acceptance_and_repeated_run_does_not_send(self):
        appointment = self.appointment()

        def accepted(*args):
            self.assertTrue(connection.in_atomic_block)
            self.assertIsNone(
                Appointment.objects.get(pk=appointment.pk).reminder_sent_at
            )
            return True

        with patch(
            "apps.whatsapp.meta.send_appointment_notification", side_effect=accepted
        ) as sender:
            self.assertEqual(booking.send_due_reminder(appointment.pk), "sent")
            appointment.refresh_from_db()
            self.assertIsNotNone(appointment.reminder_sent_at)
            self.assertEqual(booking.send_due_reminder(appointment.pk), "skipped")
        sender.assert_called_once_with(
            SYNTHETIC_PHONE, "APPOINTMENT_REMINDER", appointment.starts_at, "ar"
        )

    def test_provider_failure_leaves_reminder_retryable(self):
        appointment = self.appointment()
        self.http.return_value.request.side_effect = TimeoutError(
            "synthetic-provider-error"
        )
        self.assertEqual(booking.send_due_reminder(appointment.pk), "failed")
        appointment.refresh_from_db()
        self.assertIsNone(appointment.reminder_sent_at)
        self.http.return_value.request.side_effect = None
        self.assertEqual(booking.send_due_reminder(appointment.pk), "sent")

    def test_reminder_payload_has_no_booking_notes_patient_name_or_internal_id(self):
        appointment = self.appointment()
        self.assertEqual(booking.send_due_reminder(appointment.pk), "sent")
        payload = json.loads(self.http.return_value.request.call_args.kwargs["body"])
        self.assertEqual(payload["template"]["name"], "synthetic_reminder")
        self.assertNotIn("private-payload-sentinel", json.dumps(payload))
        self.assertNotIn("Synthetic", json.dumps(payload))
        self.assertEqual(
            set(payload["template"]["components"][0]), {"type", "parameters"}
        )
        self.assertEqual(len(payload["template"]["components"][0]["parameters"]), 2)

    def test_recheck_prevents_send_after_cancellation_or_disabling(self):
        for changes in (
            {"status": Appointment.Status.CANCELLED},
            {"reminder_enabled": False},
            {"reminder_sent_at": self.now},
        ):
            appointment = self.appointment()
            self.assertIn(
                appointment.pk,
                booking.due_reminders(self.now).values_list("pk", flat=True),
            )
            Appointment.objects.filter(pk=appointment.pk).update(**changes)
            self.assertEqual(booking.send_due_reminder(appointment.pk), "skipped")
        self.http.assert_not_called()

    def test_command_dry_run_and_missing_configuration_do_not_send(self):
        self.appointment()
        output = StringIO()
        call_command("send_whatsapp_reminders", dry_run=True, stdout=output)
        self.assertIn("Eligible reminders: 1 (dry run)", output.getvalue())
        with self.settings(WHATSAPP_META_ENABLED=False):
            with self.assertRaisesMessage(CommandError, "configuration unavailable"):
                call_command("send_whatsapp_reminders")
        with self.assertRaisesMessage(CommandError, "between 1 and 1000"):
            call_command("send_whatsapp_reminders", limit=0)
        self.http.assert_not_called()

    def test_dispatcher_requires_row_locks_and_emits_only_counts(self):
        appointment = self.appointment()
        if not connection.features.has_select_for_update:
            with self.assertRaisesMessage(CommandError, "row locking"):
                call_command("send_whatsapp_reminders")
        for result, failed in (("sent", False), ("failed", True)):
            output = StringIO()
            with patch.object(connection.features, "has_select_for_update", True):
                with patch(
                    "apps.whatsapp.management.commands.send_whatsapp_reminders.send_due_reminder",
                    return_value=result,
                ) as send:
                    if failed:
                        with self.assertRaises(CommandError):
                            call_command("send_whatsapp_reminders", stdout=output)
                    else:
                        call_command("send_whatsapp_reminders", stdout=output)
                    send.assert_called_once_with(appointment.pk)
            self.assertNotIn(SYNTHETIC_PHONE, output.getvalue())
            self.assertIn("Reminders:", output.getvalue())
        self.http.assert_not_called()

    def test_actual_reminder_query_compiles_for_update_skip_locked_on_postgresql(self):
        appointment = self.appointment()
        backend = DatabaseWrapper({}, alias="whatsapp-lock-compilation-only")
        captured = []
        execute = SQLCompiler.execute_sql

        def capture(compiler, *args, **kwargs):
            if compiler.query.select_for_update:
                sql, _ = (
                    compiler.query.clone().get_compiler(connection=backend).as_sql()
                )
                captured.append(sql)
            return execute(compiler, *args, **kwargs)

        with (
            patch.object(backend, "get_autocommit", return_value=False),
            patch.object(
                backend,
                "ensure_connection",
                side_effect=AssertionError("No PG connection"),
            ),
        ):
            with patch.object(
                connection.features, "has_select_for_update_skip_locked", True
            ):
                with patch.object(SQLCompiler, "execute_sql", capture):
                    self.assertEqual(booking.send_due_reminder(appointment.pk), "sent")
        self.assertEqual(len(captured), 1)
        self.assertIn("FOR UPDATE SKIP LOCKED", captured[0])
        self.assertNotIn("JOIN", captured[0])

    def test_confirmation_waits_for_commit_and_rollback_does_not_send(self):
        starts_at = self.now + timedelta(days=2)
        with patch(
            "apps.booking.services.validate_public_booking_request",
            return_value=(self.doctor, starts_at, starts_at + timedelta(minutes=30)),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                appointment = create_public_appointment(
                    full_name="Synthetic",
                    phone_raw=SYNTHETIC_PHONE,
                    visit_type_id=self.visit_type.pk,
                    starts_at=starts_at,
                    language="en",
                )
                self.http.assert_not_called()
        payload = json.loads(self.http.return_value.request.call_args.kwargs["body"])
        self.assertEqual(payload["template"]["name"], "synthetic_confirmation")
        self.assertEqual(payload["template"]["language"]["code"], "en_US")
        self.assertTrue(Appointment.objects.filter(pk=appointment.pk).exists())
        self.http.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                booking.schedule_booking_confirmation(appointment.pk, "ar")
                raise RuntimeError("synthetic rollback")
        self.http.assert_not_called()

    def test_confirmation_failure_preserves_booking_and_retry_deduplicates(self):
        appointment = self.appointment()
        self.http.return_value.request.side_effect = TimeoutError(
            "private-payload-sentinel"
        )
        self.assertFalse(booking.send_booking_confirmation(appointment.pk, "ar"))
        self.assertTrue(Appointment.objects.filter(pk=appointment.pk).exists())
        self.http.return_value.request.side_effect = None
        self.assertTrue(booking.send_booking_confirmation(appointment.pk, "ar"))
        self.assertTrue(booking.send_booking_confirmation(appointment.pk, "ar"))
        self.assertEqual(self.http.return_value.request.call_count, 2)

    def test_booking_form_preserves_page_language_for_confirmation(self):
        form = PublicBookingForm(language="en")
        form.cleaned_data = {
            "full_name": "Synthetic",
            "phone": SYNTHETIC_PHONE,
            "visit_type": self.visit_type,
            "starts_at": self.now,
        }
        with (
            patch.object(form, "is_valid", return_value=True),
            patch("apps.booking.forms.services.create_public_appointment") as create,
        ):
            form.save()
        self.assertEqual(create.call_args.kwargs["language"], "en")
