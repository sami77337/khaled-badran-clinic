"""Real independent database transactions exercising the shared slot-write lock."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Event, local
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from apps.booking import operations, rescheduling, services
from apps.booking.models import Appointment
from apps.booking.test_patient_rescheduling import RescheduleFixtureMixin


@skipUnlessDBFeature("has_select_for_update")
class PatientRescheduleConcurrencyTests(RescheduleFixtureMixin, TransactionTestCase):
    def _reschedule(self, token=None, starts_at=None):
        return rescheduling.patient_reschedule_appointment(
            token=token or self.token, starts_at=starts_at or self.target,
        )

    def _new_booking(self):
        return services.create_public_appointment(
            full_name="Synthetic concurrent booking", phone_raw="0795555555",
            visit_type_id=self.visit_type.pk, starts_at=self.target + timedelta(minutes=15),
        )

    def _race(self, first, second):
        acquired, attempted, release = Event(), Event(), Event()
        worker = local()
        real_lock = services.lock_booking_doctor

        def controlled_lock(doctor_id):
            if not worker.first:
                attempted.set()
            result = real_lock(doctor_id)
            if worker.first:
                acquired.set()
                if not release.wait(10):
                    raise TimeoutError("Synthetic writer was not released")
            return result

        def run(callback, is_first):
            close_old_connections()
            worker.first = is_first
            try:
                callback()
                return "accepted"
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()

        with patch("apps.booking.services.lock_booking_doctor", side_effect=controlled_lock):
            with ThreadPoolExecutor(max_workers=2) as executor:
                winner = executor.submit(run, first, True)
                try:
                    self.assertTrue(acquired.wait(5))
                    loser = executor.submit(run, second, False)
                    self.assertTrue(attempted.wait(5))
                    with self.assertRaises(TimeoutError):
                        loser.result(timeout=0.15)
                finally:
                    release.set()
                self.assertEqual(winner.result(timeout=10), "accepted")
                self.assertEqual(loser.result(timeout=10), "rejected")
        active = Appointment.objects.filter(status__in=services.ACTIVE_APPOINTMENT_STATUSES)
        self.assertEqual(active.filter(starts_at__lt=self.target + timedelta(minutes=45), ends_at__gt=self.target).count(), 1)

    def _other_no_show(self):
        return self.create_appointment(
            doctor=self.doctor, patient=self.patient, visit_type=self.visit_type,
            starts_at=self.appointment.starts_at - timedelta(days=1), status=Appointment.Status.NO_SHOW,
        )

    def test_two_patients_cannot_take_same_slot(self):
        other = self._other_no_show()
        token = rescheduling.make_reschedule_token(other)
        self._race(self._reschedule, lambda: self._reschedule(token))
        other.refresh_from_db()
        self.assertEqual(other.status, Appointment.Status.NO_SHOW)
        self.assertEqual(Appointment.objects.count(), 2)

    def test_two_patients_cannot_take_overlapping_different_starts(self):
        token = rescheduling.make_reschedule_token(self._other_no_show())
        self._race(self._reschedule, lambda: self._reschedule(token, self.target + timedelta(minutes=15)))

    def test_concurrent_replay_changes_appointment_only_once(self):
        self._race(self._reschedule, lambda: self._reschedule(starts_at=self.target + timedelta(hours=1)))
        self.assertEqual(self.appointment.status_history.count(), 2)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_public_booking_revalidates_after_patient_reschedule(self):
        self._race(self._reschedule, self._new_booking)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_patient_reschedule_revalidates_after_public_booking(self):
        self._race(self._new_booking, self._reschedule)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.NO_SHOW)
        self.assertIsNotNone(self.appointment.reminder_sent_at)
        self.assertEqual(self.appointment.status_history.count(), 1)

    def test_staff_reschedule_revalidates_after_patient_reschedule(self):
        other = self.create_appointment(
            doctor=self.doctor, patient=self.patient, visit_type=self.visit_type,
            starts_at=self.target + timedelta(days=1),
        )
        self._race(self._reschedule, lambda: operations.reschedule_appointment(
            other.pk, starts_at=self.target + timedelta(minutes=15),
        ))
