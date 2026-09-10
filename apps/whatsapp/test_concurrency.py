"""Real database/cache coordination with synthetic recipients and mocked HTTP."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys
from threading import Event
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import (
    SimpleTestCase,
    TransactionTestCase,
    override_settings,
    skipUnlessDBFeature,
)
from django.utils import timezone

from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
from apps.patients.models import Patient
from .booking import send_due_reminder
from .test_meta import META_SETTINGS, SYNTHETIC_PHONE
from .webhook import _handle_message


@override_settings(**META_SETTINGS)
class ReminderConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update_skip_locked")
    def test_overlapping_workers_send_once_and_persist_acceptance(self):
        doctor = Doctor.objects.create(
            full_name_ar="Synthetic", full_name_en="Synthetic"
        )
        patient = Patient.objects.create(
            full_name="Synthetic", phone_e164=SYNTHETIC_PHONE
        )
        visit_type = VisitType.objects.create(
            doctor=doctor, name_ar="Synthetic", name_en="Synthetic", duration_minutes=30
        )
        starts_at = timezone.now() + timedelta(hours=1)
        appointment = Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            whatsapp_phone_e164=SYNTHETIC_PHONE,
        )
        entered, release = Event(), Event()

        def accept(*args):
            entered.set()
            if not release.wait(10):
                raise TimeoutError("Synthetic worker was not released")
            return True

        def dispatch():
            close_old_connections()
            try:
                return send_due_reminder(appointment.pk)
            finally:
                connections.close_all()

        with patch(
            "apps.whatsapp.meta.send_appointment_notification", side_effect=accept
        ) as send:
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(dispatch)
                try:
                    self.assertTrue(entered.wait(5))
                    self.assertEqual(
                        workers.submit(dispatch).result(timeout=5), "skipped"
                    )
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=5), "sent")
            self.assertEqual(send_due_reminder(appointment.pk), "skipped")
            send.assert_called_once()
        appointment.refresh_from_db()
        self.assertIsNotNone(appointment.reminder_sent_at)


@override_settings(**META_SETTINGS)
@skipUnless(
    settings.CACHES["default"]["BACKEND"]
    == "django.core.cache.backends.redis.RedisCache"
    and os.environ.get("CACHE_URL"),
    "Requires an isolated Redis CACHE_URL shared with child processes",
)
class WebhookProcessCoordinationTests(SimpleTestCase):
    def test_separate_worker_observes_conversation_lock_and_completed_receipt(self):
        cache.clear()
        self.addCleanup(cache.clear)
        entered, release = Event(), Event()

        def accept(*args):
            entered.set()
            if not release.wait(20):
                raise TimeoutError("Synthetic worker was not released")
            return True

        child = """
import django
django.setup()
from django.test import override_settings
from unittest.mock import patch
from apps.whatsapp.test_meta import META_SETTINGS, SYNTHETIC_PHONE
from apps.whatsapp.webhook import _handle_message
with override_settings(**META_SETTINGS):
    with patch('apps.whatsapp.meta._send', side_effect=AssertionError('Duplicate send')):
        result = _handle_message(SYNTHETIC_PHONE.lstrip('+'), 'synthetic-process-event', '', '')
        print('accepted' if result else 'busy')
"""

        def other_worker():
            result = subprocess.run(
                [sys.executable, "-c", child],
                cwd=Path(settings.BASE_DIR),
                env={**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.dev"},
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        with patch("apps.whatsapp.meta._send", side_effect=accept) as send:
            with ThreadPoolExecutor(max_workers=1) as workers:
                first = workers.submit(
                    _handle_message,
                    SYNTHETIC_PHONE.lstrip("+"),
                    "synthetic-process-event",
                    "",
                    "",
                )
                try:
                    self.assertTrue(entered.wait(5))
                    self.assertEqual(other_worker(), "busy")
                finally:
                    release.set()
                self.assertTrue(first.result(timeout=5))
            self.assertEqual(other_worker(), "accepted")
            send.assert_called_once()
