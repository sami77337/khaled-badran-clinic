"""Synthetic-only clinical reply authorization tests for registered/guest models."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.patients.consultation_services import (
    can_author_clinical_reply,
    update_consultation_reply,
)
from apps.patients.models import Consultation, Patient, TransientConsultation


class ClinicalReplyLeastPrivilegeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.front_desk = users.objects.create_user(
            username="synthetic-front-desk", is_staff=True,
        )
        cls.doctor = users.objects.create_user(
            username="synthetic-clinician", is_staff=True,
        )
        cls.registered_only = users.objects.create_user(
            username="synthetic-registered-clinician", is_staff=True,
        )
        cls.guest_only = users.objects.create_user(
            username="synthetic-guest-clinician", is_staff=True,
        )
        cls.superuser = users.objects.create_superuser(
            username="synthetic-clinical-superuser",
            password="Synthetic-Test-Password-981!",
        )
        cls.patient_user = users.objects.create_user(username="synthetic-patient")
        cls.patient = Patient.objects.create(
            user=cls.patient_user, full_name="Synthetic consultation patient",
        )
        cls.registered = Consultation.objects.create(
            patient=cls.patient, question="Synthetic private registered question",
        )
        cls.guest = TransientConsultation.objects.create(
            phone_e164="+12025550101", question="Synthetic private guest question",
        )

        registered_permission = Permission.objects.get(
            content_type__app_label="patients", codename="change_consultation",
        )
        guest_permission = Permission.objects.get(
            content_type__app_label="patients", codename="change_transientconsultation",
        )
        cls.doctor.user_permissions.add(registered_permission, guest_permission)
        cls.registered_only.user_permissions.add(registered_permission)
        cls.guest_only.user_permissions.add(guest_permission)

    def _cases(self):
        return (
            (self.registered, False, "dashboard_consultation_detail"),
            (self.guest, True, "dashboard_guest_consultation_detail"),
        )

    def test_independent_django_permissions_define_authorship(self):
        for guest in (False, True):
            with self.subTest(guest=guest):
                self.assertFalse(can_author_clinical_reply(self.patient_user, guest=guest))
                self.assertFalse(can_author_clinical_reply(self.front_desk, guest=guest))
                self.assertTrue(can_author_clinical_reply(self.doctor, guest=guest))
                self.assertTrue(can_author_clinical_reply(self.superuser, guest=guest))
        self.assertTrue(can_author_clinical_reply(self.registered_only))
        self.assertFalse(can_author_clinical_reply(self.registered_only, guest=True))
        self.assertFalse(can_author_clinical_reply(self.guest_only))
        self.assertTrue(can_author_clinical_reply(self.guest_only, guest=True))
        self.doctor.is_active = False
        self.assertFalse(can_author_clinical_reply(self.doctor))
        self.assertFalse(can_author_clinical_reply(self.doctor, guest=True))

    def test_front_desk_cannot_submit_text_or_audio_via_ar_en_dashboard(self):
        self.client.force_login(self.front_desk)
        for consultation, guest, route in self._cases():
            for language in ("ar", "en"):
                with self.subTest(guest=guest, language=language):
                    url = reverse(route, kwargs={"public_id": consultation.public_id})
                    if language == "en":
                        url += "?lang=en"
                    page = self.client.get(url)
                    self.assertEqual(page.status_code, 200)
                    self.assertContains(page, "data-consultation-read-only")
                    self.assertNotContains(page, "data-consultation-reply-form")
                    self.assertNotContains(page, "data-consultation-audio-recorder")

                    response = self.client.post(
                        url, {"status": "answered", "staff_reply": "Unauthorized synthetic reply"},
                    )
                    self.assertEqual(response.status_code, 403)
                    consultation.refresh_from_db()
                    self.assertEqual(consultation.staff_reply, "")
                    self.assertEqual(consultation.status, consultation.Status.NEW)
                    self.assertIsNone(consultation.replied_at)

    def test_service_rejects_staff_without_permission_even_if_view_bypassed(self):
        for consultation, guest, _ in self._cases():
            with self.subTest(guest=guest):
                with self.assertRaises(PermissionDenied):
                    update_consultation_reply(
                        consultation=consultation,
                        staff_user=self.front_desk,
                        reply="Synthetic bypass attempt",
                        status=consultation.Status.ANSWERED,
                    )
                consultation.refresh_from_db()
                self.assertEqual(consultation.staff_reply, "")

    def test_single_model_permission_cannot_author_another_type(self):
        for consultation, guest, route in self._cases():
            allowed = self.guest_only if guest else self.registered_only
            denied = self.registered_only if guest else self.guest_only
            url = reverse(route, kwargs={"public_id": consultation.public_id})

            self.client.force_login(denied)
            self.assertEqual(self.client.post(
                url, {"staff_reply": "Unapproved", "status": "answered"},
            ).status_code, 403)

            self.client.force_login(allowed)
            self.assertContains(self.client.get(url), "data-consultation-reply-form")
            self.assertEqual(self.client.post(
                url, {"staff_reply": "Synthetic authorized reply", "status": "answered"},
            ).status_code, 302)
            consultation.refresh_from_db()
            self.assertEqual(consultation.staff_reply, "Synthetic authorized reply")
            self.assertEqual(consultation.replied_by_id, allowed.pk)

    def test_superuser_retains_regular_django_model_permission_semantics(self):
        self.client.force_login(self.superuser)
        for consultation, guest, route in self._cases():
            with self.subTest(guest=guest):
                url = reverse(route, kwargs={"public_id": consultation.public_id})
                self.assertContains(self.client.get(url), "data-consultation-reply-form")
                self.assertEqual(self.client.post(
                    url, {"staff_reply": "Synthetic supervised reply", "status": "answered"},
                ).status_code, 302)
