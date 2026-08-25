from datetime import date, datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.booking import services as booking_services
from apps.booking.models import Appointment
from apps.clinic.models import (
    ClosedDay,
    Doctor,
    DoctorSchedule,
    DoctorScheduleOverride,
    VisitType,
)
from apps.core.models import AuditLog, SystemSetting
from apps.dashboard import views as dashboard_views
from apps.patients.models import Patient
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord


class DashboardRecordWorkflowMixin:
    @classmethod
    def setUpClass(cls):
        cls._private_media_tempdir = TemporaryDirectory()
        cls._private_media_override = override_settings(
            PRIVATE_MEDIA_ROOT=Path(cls._private_media_tempdir.name)
        )
        cls._private_media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._private_media_override.disable()
        cls._private_media_tempdir.cleanup()

    def create_user(self, username="synthetic-dashboard-user", *, is_staff=False):
        return get_user_model().objects.create_user(username=username, is_staff=is_staff)

    def create_staff(self):
        return self.create_user(username="Synthetic Staff", is_staff=True)

    def create_patient(
        self,
        *,
        user=None,
        full_name="Synthetic Patient",
        phone_raw="+962700000000",
        phone_e164="+962700000000",
    ):
        return Patient.objects.create(
            user=user,
            full_name=full_name,
            phone_raw=phone_raw,
            phone_e164=phone_e164,
            date_of_birth=date(1990, 1, 1),
            gender=Patient.Gender.PREFER_NOT_TO_SAY,
        )

    def create_doctor(self):
        return Doctor.objects.create(
            full_name_ar="Synthetic Doctor",
            full_name_en="Synthetic Doctor",
            title_en="Dr.",
            specialty_en="Synthetic clinic care",
            is_active=True,
        )

    def create_visit_type(self, doctor=None):
        return VisitType.objects.create(
            doctor=doctor or self.create_doctor(),
            name_ar="Synthetic visit",
            name_en="Synthetic visit",
            duration_minutes=30,
            is_active=True,
        )

    def create_appointment(self, patient):
        doctor = self.create_doctor()
        visit_type = self.create_visit_type(doctor=doctor)
        starts_at = timezone.now() + timedelta(days=1)
        return Appointment.objects.create(
            doctor=doctor,
            patient=patient,
            visit_type=visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=visit_type.duration_minutes),
        )

    def create_visit(self, *, patient=None, appointment=None, **kwargs):
        patient = patient or self.create_patient()
        return VisitRecord.objects.create(
            patient=patient,
            appointment=appointment,
            visit_reason=kwargs.pop("visit_reason", "Synthetic visit reason."),
            doctor_notes=kwargs.pop("doctor_notes", "Synthetic doctor note."),
            diagnosis_plan=kwargs.pop("diagnosis_plan", "Synthetic manual plan."),
            instructions=kwargs.pop("instructions", "Synthetic instructions."),
            follow_up_notes=kwargs.pop("follow_up_notes", "Synthetic follow-up."),
            **kwargs,
        )

    def create_note(self, *, patient=None, visit=None, **kwargs):
        patient = patient or self.create_patient()
        return ClinicalNote.objects.create(
            patient=patient,
            visit=visit,
            title=kwargs.pop("title", "Synthetic note title"),
            body=kwargs.pop("body", "Synthetic note body."),
            **kwargs,
        )

    def synthetic_image_file(
        self,
        name="synthetic-dashboard-image.jpg",
        content=b"synthetic-image-bytes",
        content_type="image/jpeg",
    ):
        return SimpleUploadedFile(name, content, content_type=content_type)

    def synthetic_video_file(
        self,
        name="synthetic-dashboard-video.mp4",
        content=b"synthetic-video-bytes",
        content_type="video/mp4",
    ):
        return SimpleUploadedFile(name, content, content_type=content_type)

    def create_media(self, *, patient=None, media_type=RecordMedia.MediaType.IMAGE, file=None, **kwargs):
        patient = patient or self.create_patient()
        if file is None:
            file = (
                self.synthetic_video_file()
                if media_type == RecordMedia.MediaType.SHORT_VIDEO
                else self.synthetic_image_file()
            )
        return RecordMedia.objects.create(
            patient=patient,
            media_type=media_type,
            file=file,
            title=kwargs.pop("title", "Synthetic dashboard media title"),
            description=kwargs.pop("description", "Synthetic dashboard media description."),
            **kwargs,
        )

    def assert_no_cache(self, response):
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)


class DashboardRecordAccessTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.patient = self.create_patient()
        self.staff = self.create_staff()
        self.normal_user = self.create_user(username="synthetic-dashboard-normal-user")

    def test_anonymous_cannot_access_dashboard_patient_list(self):
        response = self.client.get(reverse("dashboard_patient_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", response["Location"])

    def test_authenticated_non_staff_gets_403_for_dashboard_patient_list(self):
        self.client.force_login(self.normal_user)

        response = self.client.get(reverse("dashboard_patient_list"))

        self.assertEqual(response.status_code, 403)

    def test_staff_can_access_dashboard_patient_list(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("dashboard_patient_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)
        self.assertContains(response, self.patient.phone)
        self.assert_no_cache(response)

    def test_anonymous_cannot_access_patient_record_detail(self):
        response = self.client.get(
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", response["Location"])

    def test_non_staff_cannot_access_patient_record_detail(self):
        self.client.force_login(self.normal_user)

        response = self.client.get(
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id})
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_can_access_patient_record_detail(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient.full_name)
        self.assertContains(response, self.patient.phone)
        self.assert_no_cache(response)


class DashboardPatientRecordDetailTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.patient = self.create_patient()
        self.other_patient = self.create_patient(
            full_name="Synthetic Other Patient",
            phone_raw="+962700000001",
            phone_e164="+962700000001",
        )
        self.client.force_login(self.staff)

    def test_staff_sees_selected_patient_records_and_not_another_patient_records(self):
        visit = self.create_visit(patient=self.patient, visit_reason="Selected patient visit reason.")
        self.create_note(patient=self.patient, visit=visit, title="Selected patient note", body="Selected note body.")
        private_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
            title="Selected private media",
        )
        visible_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Selected patient-visible media",
        )
        public_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            title="Selected approved public media",
        )
        inactive_public_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            is_active=False,
            title="Selected inactive public media",
        )
        self.create_visit(patient=self.other_patient, visit_reason="Other patient visit reason hidden.")
        self.create_note(patient=self.other_patient, title="Other patient note hidden.")
        self.create_media(patient=self.other_patient, title="Other patient media hidden.")

        response = self.client.get(
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id})
        )

        self.assertContains(response, "Selected patient visit reason.")
        self.assertContains(response, "Selected patient note")
        self.assertContains(response, "Selected private media")
        self.assertContains(response, "Selected patient-visible media")
        self.assertContains(response, "Selected approved public media")
        self.assertContains(response, "Selected inactive public media")
        self.assertNotContains(response, "Other patient visit reason hidden.")
        self.assertNotContains(response, "Other patient note hidden.")
        self.assertNotContains(response, "Other patient media hidden.")

        private_staff_url = reverse(
            "record_private_media_download",
            kwargs={"public_id": private_media.public_id},
        )
        visible_staff_url = reverse(
            "record_private_media_download",
            kwargs={"public_id": visible_media.public_id},
        )
        public_case_url = reverse("public_case_media", kwargs={"public_id": public_media.public_id})
        visible_public_url = reverse("public_case_media", kwargs={"public_id": visible_media.public_id})
        inactive_public_url = reverse("public_case_media", kwargs={"public_id": inactive_public_media.public_id})
        self.assertContains(response, f'href="{private_staff_url}"')
        self.assertContains(response, f'href="{visible_staff_url}"')
        self.assertContains(response, f'href="{public_case_url}"')
        self.assertNotContains(response, f'href="{visible_public_url}"')
        self.assertNotContains(response, f'href="{inactive_public_url}"')

        for expected_label in ["خاص فقط", "ظاهر للمريض", "حالة عامة بموافقة", "موافقة مؤكدة", "غير نشط"]:
            with self.subTest(expected_label=expected_label):
                self.assertContains(response, expected_label)

        blocked_fragments = [
            private_media.file.name,
            visible_media.file.name,
            public_media.file.name,
            "synthetic-dashboard-image.jpg",
            str(Path(private_media.file.storage.location)),
            'href="/media/',
        ]
        for fragment in blocked_fragments:
            with self.subTest(fragment=fragment):
                self.assertNotContains(response, fragment)
        with self.assertRaises(ValueError):
            private_media.file.url


class DashboardCreateWorkflowTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.patient = self.create_patient()
        self.client.force_login(self.staff)

    def test_staff_can_create_visit_record_with_private_default(self):
        response = self.client.post(
            reverse("dashboard_visit_create", kwargs={"patient_id": self.patient.id}),
            {
                "appointment": "",
                "visit_date": "2026-01-15T10:30",
                "visit_reason": "Synthetic dashboard visit reason.",
                "doctor_notes": "Synthetic dashboard doctor note.",
                "diagnosis_plan": "Synthetic dashboard manual plan.",
                "instructions": "Synthetic dashboard instructions.",
                "follow_up_notes": "Synthetic dashboard follow-up.",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id}),
            fetch_redirect_response=False,
        )
        visit = VisitRecord.objects.get(patient=self.patient)
        self.assertFalse(visit.is_visible_to_patient)
        self.assertEqual(visit.visit_reason, "Synthetic dashboard visit reason.")

    def test_staff_can_create_clinical_note(self):
        visit = self.create_visit(patient=self.patient)

        response = self.client.post(
            reverse("dashboard_note_create", kwargs={"patient_id": self.patient.id}),
            {
                "visit": str(visit.id),
                "note_type": ClinicalNote.NoteType.STAFF_NOTE,
                "title": "Synthetic dashboard note",
                "body": "Synthetic dashboard note body.",
                "is_visible_to_patient": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id}),
            fetch_redirect_response=False,
        )
        note = ClinicalNote.objects.get(patient=self.patient)
        self.assertEqual(note.created_by, self.staff)
        self.assertTrue(note.is_visible_to_patient)
        self.assertEqual(note.visit, visit)

    def test_staff_can_upload_valid_image_record_media(self):
        response = self.client.post(
            reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id}),
            {
                "visit": "",
                "media_type": RecordMedia.MediaType.IMAGE,
                "file": self.synthetic_image_file(content=b"image-bytes"),
                "title": "Synthetic uploaded dashboard image",
                "description": "Synthetic dashboard image description.",
                "visibility": RecordMedia.Visibility.PRIVATE_ONLY,
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id}),
            fetch_redirect_response=False,
        )
        media = RecordMedia.objects.get(patient=self.patient)
        self.assertEqual(media.uploaded_by, self.staff)
        self.assertEqual(media.media_type, RecordMedia.MediaType.IMAGE)
        self.assertEqual(media.content_type, "image/jpeg")
        self.assertEqual(media.original_filename, "synthetic-dashboard-image.jpg")

    def test_staff_can_upload_valid_short_mp4_record_media(self):
        response = self.client.post(
            reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id}),
            {
                "visit": "",
                "media_type": RecordMedia.MediaType.SHORT_VIDEO,
                "file": self.synthetic_video_file(content=b"video-bytes"),
                "title": "Synthetic uploaded dashboard video",
                "description": "Synthetic dashboard video description.",
                "visibility": RecordMedia.Visibility.PRIVATE_ONLY,
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id}),
            fetch_redirect_response=False,
        )
        media = RecordMedia.objects.get(patient=self.patient)
        self.assertEqual(media.uploaded_by, self.staff)
        self.assertEqual(media.media_type, RecordMedia.MediaType.SHORT_VIDEO)
        self.assertEqual(media.content_type, "video/mp4")
        self.assertEqual(media.original_filename, "synthetic-dashboard-video.mp4")

    def test_invalid_media_upload_shows_form_error_and_does_not_create_record(self):
        response = self.client.post(
            reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id}),
            {
                "visit": "",
                "media_type": RecordMedia.MediaType.IMAGE,
                "file": self.synthetic_image_file(
                    name="synthetic-dashboard-image.gif",
                    content_type="image/gif",
                ),
                "title": "Invalid dashboard media",
                "description": "Synthetic invalid dashboard media.",
                "visibility": RecordMedia.Visibility.PRIVATE_ONLY,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Unsupported image", status_code=400)
        self.assertEqual(RecordMedia.objects.filter(patient=self.patient).count(), 0)

    def test_approved_public_case_without_consent_is_rejected(self):
        response = self.client.post(
            reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id}),
            {
                "visit": "",
                "media_type": RecordMedia.MediaType.IMAGE,
                "file": self.synthetic_image_file(),
                "title": "Unconsented dashboard public media",
                "description": "Synthetic unconsented public media.",
                "visibility": RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Public case media requires confirmed consent.", status_code=400)
        self.assertEqual(RecordMedia.objects.filter(patient=self.patient).count(), 0)

    def test_dashboard_posts_are_csrf_protected(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)

        response = csrf_client.post(
            reverse("dashboard_visit_create", kwargs={"patient_id": self.patient.id}),
            {
                "appointment": "",
                "visit_date": "2026-01-15T10:30",
                "visit_reason": "Synthetic dashboard visit reason.",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_visible_to_patient_and_private_only_media_do_not_become_public(self):
        portal_user = self.create_user(username="synthetic-dashboard-linked-user")
        self.patient.user = portal_user
        self.patient.save(update_fields=["user"])
        visible_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Synthetic visible media is not public",
        )
        private_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
            title="Synthetic private media is not patient visible",
        )

        public_response = self.client.get(
            reverse("public_case_media", kwargs={"public_id": visible_media.public_id})
        )
        patient_client = Client()
        patient_client.force_login(portal_user)
        private_patient_response = patient_client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": private_media.public_id},
            )
        )

        self.assertEqual(public_response.status_code, 404)
        self.assertEqual(private_patient_response.status_code, 404)


class DashboardUpdateWorkflowTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.patient_user = self.create_user(username="synthetic-dashboard-patient-user")
        self.patient = self.create_patient(user=self.patient_user)
        self.client.force_login(self.staff)

    def media_update_url(self, media):
        return reverse(
            "dashboard_media_update",
            kwargs={"patient_id": self.patient.id, "public_id": media.public_id},
        )

    def test_staff_can_update_media_title_description_and_visibility(self):
        media = self.create_media(patient=self.patient, visibility=RecordMedia.Visibility.PRIVATE_ONLY)

        response = self.client.post(
            self.media_update_url(media),
            {
                "title": "Updated dashboard media title",
                "description": "Updated dashboard media description.",
                "visibility": RecordMedia.Visibility.VISIBLE_TO_PATIENT,
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id}),
            fetch_redirect_response=False,
        )
        media.refresh_from_db()
        self.assertEqual(media.title, "Updated dashboard media title")
        self.assertEqual(media.description, "Updated dashboard media description.")
        self.assertEqual(media.visibility, RecordMedia.Visibility.VISIBLE_TO_PATIENT)

    def test_staff_can_mark_media_visible_to_patient_for_linked_patient_only(self):
        media = self.create_media(patient=self.patient, visibility=RecordMedia.Visibility.PRIVATE_ONLY)

        self.client.post(
            self.media_update_url(media),
            {
                "title": media.title,
                "description": media.description,
                "visibility": RecordMedia.Visibility.VISIBLE_TO_PATIENT,
                "is_active": "on",
            },
        )
        media.refresh_from_db()

        patient_client = Client()
        patient_client.force_login(self.patient_user)
        own_response = patient_client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": media.public_id},
            )
        )
        other_user = self.create_user(username="synthetic-dashboard-other-portal-user")
        other_client = Client()
        other_client.force_login(other_user)
        other_response = other_client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": media.public_id},
            )
        )

        self.assertEqual(media.visibility, RecordMedia.Visibility.VISIBLE_TO_PATIENT)
        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(other_response.status_code, 404)
        own_response.close()

    def test_staff_can_mark_media_approved_public_case_only_with_confirmed_consent(self):
        media = self.create_media(patient=self.patient, visibility=RecordMedia.Visibility.PRIVATE_ONLY)

        rejected = self.client.post(
            self.media_update_url(media),
            {
                "title": media.title,
                "description": media.description,
                "visibility": RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                "is_active": "on",
            },
        )
        media.refresh_from_db()
        accepted = self.client.post(
            self.media_update_url(media),
            {
                "title": media.title,
                "description": media.description,
                "visibility": RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                "consent_confirmed": "on",
                "is_active": "on",
            },
        )
        media.refresh_from_db()
        public_response = self.client.get(
            reverse("public_case_media", kwargs={"public_id": media.public_id})
        )
        patient_response = self.client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": media.public_id},
            )
        )

        self.assertEqual(rejected.status_code, 400)
        self.assertContains(rejected, "Public case media requires confirmed consent.", status_code=400)
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(media.visibility, RecordMedia.Visibility.APPROVED_PUBLIC_CASE)
        self.assertTrue(media.consent_confirmed)
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(patient_response.status_code, 404)
        public_response.close()

    def test_staff_can_deactivate_media_and_patient_or_public_routes_stop_serving(self):
        visible_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Synthetic visible media to deactivate",
        )
        public_media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            title="Synthetic public media to deactivate",
        )
        patient_client = Client()
        patient_client.force_login(self.patient_user)

        visible_before = patient_client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": visible_media.public_id},
            )
        )
        public_before = self.client.get(
            reverse("public_case_media", kwargs={"public_id": public_media.public_id})
        )
        visible_before.close()
        public_before.close()

        self.client.post(
            self.media_update_url(visible_media),
            {
                "title": visible_media.title,
                "description": visible_media.description,
                "visibility": RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            },
        )
        self.client.post(
            self.media_update_url(public_media),
            {
                "title": public_media.title,
                "description": public_media.description,
                "visibility": RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                "consent_confirmed": "on",
            },
        )
        visible_media.refresh_from_db()
        public_media.refresh_from_db()
        visible_after = patient_client.get(
            reverse(
                "patient_portal_medical_record_media_download",
                kwargs={"public_id": visible_media.public_id},
            )
        )
        public_after = self.client.get(
            reverse("public_case_media", kwargs={"public_id": public_media.public_id})
        )

        self.assertFalse(visible_media.is_active)
        self.assertFalse(public_media.is_active)
        self.assertEqual(visible_before.status_code, 200)
        self.assertEqual(public_before.status_code, 200)
        self.assertEqual(visible_after.status_code, 404)
        self.assertEqual(public_after.status_code, 404)

    def test_non_staff_cannot_post_media_changes(self):
        media = self.create_media(patient=self.patient, visibility=RecordMedia.Visibility.PRIVATE_ONLY)
        normal_user = self.create_user(username="synthetic-dashboard-non-staff-post-user")
        self.client.force_login(normal_user)

        response = self.client.post(
            self.media_update_url(media),
            {
                "title": "Blocked title",
                "description": "Blocked description.",
                "visibility": RecordMedia.Visibility.VISIBLE_TO_PATIENT,
                "is_active": "on",
            },
        )
        media.refresh_from_db()

        self.assertEqual(response.status_code, 403)
        self.assertNotEqual(media.title, "Blocked title")


class DashboardRegressionTests(DashboardRecordWorkflowMixin, TestCase):
    def test_patient_portal_medical_records_remain_read_only(self):
        patient_user = self.create_user(username="synthetic-dashboard-read-only-user")
        self.create_patient(user=patient_user)
        self.client.force_login(patient_user)

        response = self.client.post(reverse("patient_portal_medical_records"))

        self.assertEqual(response.status_code, 405)

    def test_public_cases_still_show_only_approved_consented_active_media(self):
        patient = self.create_patient()
        approved = self.create_media(
            patient=patient,
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            title="Synthetic approved dashboard public case",
        )
        self.create_media(
            patient=patient,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            title="Synthetic patient visible dashboard media hidden from public",
        )
        self.create_media(
            patient=patient,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
            title="Synthetic private dashboard media hidden from public",
        )
        self.create_media(
            patient=patient,
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            is_active=False,
            title="Synthetic inactive dashboard public media hidden",
        )

        response = self.client.get(reverse("public_cases_en"))

        self.assertContains(response, approved.title)
        self.assertNotContains(response, "Synthetic patient visible dashboard media hidden from public")
        self.assertNotContains(response, "Synthetic private dashboard media hidden from public")
        self.assertNotContains(response, "Synthetic inactive dashboard public media hidden")

    def test_staff_private_media_route_remains_staff_only(self):
        media = self.create_media()
        normal_user = self.create_user(username="synthetic-dashboard-route-normal-user")

        anonymous_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )
        self.client.force_login(normal_user)
        normal_response = self.client.get(
            reverse("record_private_media_download", kwargs={"public_id": media.public_id})
        )

        self.assertEqual(anonymous_response.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", anonymous_response["Location"])
        self.assertEqual(normal_response.status_code, 403)

    def test_records_root_upload_whatsapp_and_payment_routes_remain_absent(self):
        blocked_paths = [
            "/records/",
            "/uploads/",
            "/portal/uploads/",
            "/whatsapp/webhook/",
            "/api/whatsapp/",
            "/whatsapp/api/",
            "/payments/",
            "/portal/payments/",
        ]

        for path in blocked_paths:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 404)


class DashboardOverviewTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.doctor = Doctor.objects.create(
            full_name_ar="خالد بدران",
            full_name_en="Khaled Badran",
            title_ar="د.",
            title_en="Dr.",
            specialty_ar="استشاري الأنف والأذن والحنجرة",
            specialty_en="ENT Consultant",
            is_active=True,
        )
        self.visit_type = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="استشارة الأنف والأذن والحنجرة",
            name_en="Ear, nose and throat consultation",
            duration_minutes=30,
            is_active=True,
        )

    def local_datetime(self, *, day_offset=0, hour=10, minute=0):
        local_date = timezone.localdate() + timedelta(days=day_offset)
        naive = datetime.combine(local_date, time(hour=hour, minute=minute))
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def create_overview_patient(self, index=0, *, full_name=None):
        return self.create_patient(
            full_name=full_name or f"Overview Patient {index}",
            phone_raw=f"+96270000{index:04d}",
            phone_e164=f"+96270000{index:04d}",
        )

    def create_overview_appointment(
        self,
        starts_at,
        *,
        status=Appointment.Status.CONFIRMED,
        patient=None,
        booking_note="",
    ):
        patient = patient or self.create_overview_patient(
            Patient.objects.count() + 1
        )
        return Appointment.objects.create(
            doctor=self.doctor,
            patient=patient,
            visit_type=self.visit_type,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=self.visit_type.duration_minutes),
            status=status,
            booking_note=booking_note,
        )

    def dashboard(self, *, language="ar"):
        self.client.force_login(self.staff)
        query = {"lang": "en"} if language == "en" else {}
        return self.client.get(reverse("dashboard_home"), query)

    def test_dashboard_home_route_uses_staff_boundary_and_never_cache(self):
        route = reverse("dashboard_home")

        anonymous_ar = self.client.get(route)
        ar_location = urlsplit(anonymous_ar["Location"])
        ar_query = parse_qs(ar_location.query)
        self.assertEqual(anonymous_ar.status_code, 302)
        self.assertEqual(ar_location.path, reverse("login"))
        self.assertEqual(ar_query["role"], ["doctor"])
        self.assertEqual(ar_query["next"], [route])

        anonymous_en = self.client.get(route, {"lang": "en"})
        en_location = urlsplit(anonymous_en["Location"])
        en_query = parse_qs(en_location.query)
        self.assertEqual(anonymous_en.status_code, 302)
        self.assertEqual(en_location.path, reverse("login_en"))
        self.assertEqual(en_query["role"], ["doctor"])
        self.assertEqual(en_query["next"], [f"{route}?lang=en"])

        normal_user = self.create_user(username="overview-non-staff")
        self.client.force_login(normal_user)
        forbidden = self.client.get(route)
        self.assertEqual(forbidden.status_code, 403)

        response = self.dashboard()
        self.assertEqual(response.status_code, 200)
        self.assert_no_cache(response)

    def test_dashboard_home_renders_arabic_rtl_english_ltr_and_language_switch(self):
        arabic = self.dashboard(language="ar")
        english = self.dashboard(language="en")

        self.assertContains(arabic, '<html lang="ar" dir="rtl">')
        self.assertContains(arabic, "مرحباً مجدداً، د. خالد")
        self.assertContains(arabic, f'href="{reverse("dashboard_home")}?lang=en"')
        self.assertContains(english, '<html lang="en" dir="ltr">')
        self.assertContains(english, "Welcome back, Dr. Khaled")
        self.assertContains(english, f'href="{reverse("dashboard_home")}"')

    def test_dashboard_metrics_count_real_statuses_and_exclude_inactive_today(self):
        status_hours = (
            (Appointment.Status.CONFIRMED, 8),
            (Appointment.Status.ARRIVED, 9),
            (Appointment.Status.COMPLETED, 10),
            (Appointment.Status.NO_SHOW, 11),
            (Appointment.Status.CANCELLED, 12),
            (Appointment.Status.RESCHEDULED, 13),
        )
        for status, hour in status_hours:
            self.create_overview_appointment(
                self.local_datetime(hour=hour),
                status=status,
            )

        response = self.dashboard()

        metrics = response.context["dashboard_metrics"]
        self.assertEqual(metrics["today"], 4)
        self.assertEqual(metrics["patients"], 6)
        self.assertEqual(metrics["completed"], 1)
        self.assertEqual(metrics["no_show"], 1)
        self.assertNotContains(response, "+2 from yesterday")
        self.assertNotContains(response, "+12 this month")
        self.assertNotContains(response, "1,204")

    def test_upcoming_metric_uses_after_now_through_seven_days_and_active_statuses(self):
        patient = self.create_overview_patient(1)
        now = timezone.now()
        cases = (
            (now + timedelta(hours=1), Appointment.Status.CONFIRMED),
            (now + timedelta(days=6), Appointment.Status.ARRIVED),
            (now + timedelta(days=7, minutes=-1), Appointment.Status.CONFIRMED),
            (now - timedelta(hours=1), Appointment.Status.CONFIRMED),
            (now + timedelta(days=7, minutes=5), Appointment.Status.CONFIRMED),
            (now + timedelta(days=2), Appointment.Status.COMPLETED),
            (now + timedelta(days=3), Appointment.Status.NO_SHOW),
            (now + timedelta(days=4), Appointment.Status.CANCELLED),
            (now + timedelta(days=5), Appointment.Status.RESCHEDULED),
        )
        for starts_at, status in cases:
            self.create_overview_appointment(
                starts_at,
                status=status,
                patient=patient,
            )

        response = self.dashboard(language="en")

        self.assertEqual(response.context["dashboard_metrics"]["upcoming"], 3)
        self.assertContains(response, "Next 7 days")

    def test_total_patient_metric_uses_patient_count(self):
        for index in range(3):
            self.create_overview_patient(index)

        response = self.dashboard()

        self.assertEqual(response.context["dashboard_metrics"]["patients"], 3)

    def test_today_schedule_is_chronological_bounded_and_excludes_inactive_rows(self):
        included_names = []
        for index, hour in enumerate(range(7, 15)):
            patient_name = (
                "A very long operational patient name that must wrap safely without horizontal overflow"
                if index == 0
                else f"Scheduled Patient {index}"
            )
            patient = self.create_overview_patient(index, full_name=patient_name)
            included_names.append(patient_name)
            self.create_overview_appointment(
                self.local_datetime(hour=hour),
                patient=patient,
                status=(
                    Appointment.Status.COMPLETED
                    if index == 1
                    else Appointment.Status.NO_SHOW
                    if index == 2
                    else Appointment.Status.CONFIRMED
                ),
            )
        cancelled_patient = self.create_overview_patient(20, full_name="Cancelled Overview Patient")
        rescheduled_patient = self.create_overview_patient(21, full_name="Rescheduled Overview Patient")
        self.create_overview_appointment(
            self.local_datetime(hour=16),
            patient=cancelled_patient,
            status=Appointment.Status.CANCELLED,
        )
        self.create_overview_appointment(
            self.local_datetime(hour=17),
            patient=rescheduled_patient,
            status=Appointment.Status.RESCHEDULED,
        )

        response = self.dashboard(language="en")
        schedule = response.context["schedule_items"]

        self.assertEqual(len(schedule), 6)
        self.assertEqual(
            [item["appointment"].patient.full_name for item in schedule],
            included_names[:6],
        )
        for patient_name in included_names[:6]:
            self.assertContains(response, patient_name)
        self.assertNotContains(response, included_names[6])
        self.assertNotContains(response, included_names[7])
        self.assertNotContains(response, cancelled_patient.full_name)
        self.assertNotContains(response, rescheduled_patient.full_name)
        self.assertContains(response, self.visit_type.name_en)
        self.assertContains(response, "Completed")
        self.assertContains(response, "No-show")

    def test_today_schedule_related_data_does_not_add_per_row_queries(self):
        patient = self.create_overview_patient(30)
        for index, hour in enumerate(range(8, 14)):
            self.create_overview_appointment(
                self.local_datetime(hour=hour, minute=index),
                patient=patient,
            )
        request = RequestFactory().get(reverse("dashboard_home"))
        request.user = self.staff

        with CaptureQueriesContext(connection) as captured_queries:
            response = dashboard_views.dashboard_home(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured_queries), 6)

    def test_today_schedule_empty_state_is_bilingual_and_has_no_fake_rows(self):
        arabic = self.dashboard(language="ar")
        english = self.dashboard(language="en")

        self.assertContains(arabic, "لا توجد مواعيد لليوم.")
        self.assertContains(english, "No appointments scheduled for today.")
        self.assertNotContains(arabic, "Synthetic Patient A")
        self.assertNotContains(english, "Synthetic Patient B")

    def test_overview_omits_private_patient_and_record_fields(self):
        patient_user = self.create_user(username="overview-private-patient-user")
        patient_user.email = "overview-private-email@example.test"
        patient_user.save(update_fields=["email"])
        patient = Patient.objects.create(
            id=938475,
            user=patient_user,
            full_name="Operational Patient Name",
            phone_raw="0791234987",
            phone_e164="+962791234987",
            notes="OVERVIEW-PRIVATE-PATIENT-NOTES",
        )
        appointment = self.create_overview_appointment(
            self.local_datetime(hour=14),
            patient=patient,
            booking_note="OVERVIEW-PRIVATE-BOOKING-NOTE",
        )
        visit = self.create_visit(
            patient=patient,
            appointment=appointment,
            doctor_notes="OVERVIEW-PRIVATE-DOCTOR-NOTES",
        )
        self.create_note(
            patient=patient,
            visit=visit,
            body="OVERVIEW-PRIVATE-CLINICAL-NOTE",
        )
        media = self.create_media(
            patient=patient,
            file=self.synthetic_image_file(name="overview-private-media.jpg"),
            title="OVERVIEW-PRIVATE-MEDIA-TITLE",
        )

        response = self.dashboard()
        page = response.content.decode()
        head = page.split("</head>", 1)[0]

        self.assertContains(response, patient.full_name)
        self.assertNotIn(patient.full_name, head)
        for private_value in (
            patient.phone_raw,
            patient.phone_e164,
            patient_user.email,
            patient.notes,
            appointment.booking_note,
            visit.doctor_notes,
            "OVERVIEW-PRIVATE-CLINICAL-NOTE",
            media.title,
            str(media.public_id),
            str(appointment.public_token),
            "overview-private-media.jpg",
            str(patient.id),
        ):
            self.assertNotContains(response, private_value)

    def test_dashboard_navigation_has_only_current_real_routes(self):
        response = self.dashboard(language="en")

        self.assertContains(response, f'href="{reverse("dashboard_home")}?lang=en"')
        self.assertContains(response, f'href="{reverse("staff_appointment_list")}"')
        self.assertContains(response, f'href="{reverse("dashboard_patient_list")}"')
        self.assertContains(response, f'href="{reverse("dashboard_scheduling")}?lang=en"')
        for unavailable_label in (
            "Medical Records",
            "Clinic Settings",
            "Content",
            "Reviews",
            "New Patient",
            "Edit Clinic Schedule",
            "Update Website Content",
        ):
            self.assertNotContains(response, unavailable_label)

    def test_mobile_drawer_has_accessible_rtl_ltr_controls_and_keyboard_close(self):
        response = self.dashboard()
        project_root = Path(__file__).resolve().parents[2]
        javascript = (project_root / "static" / "js" / "dashboard.js").read_text(
            encoding="utf-8"
        )
        stylesheet = (project_root / "static" / "css" / "dashboard.css").read_text(
            encoding="utf-8"
        )

        self.assertContains(response, 'aria-controls="dashboard-sidebar"')
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, 'id="dashboard-sidebar"')
        self.assertContains(response, "data-dashboard-overlay")
        self.assertIn('event.key === "Escape"', javascript)
        self.assertIn('document.body.classList.add("dashboard-drawer-open")', javascript)
        self.assertIn('sidebar.querySelectorAll("a[href]")', javascript)
        self.assertIn('[dir="rtl"] .dashboard-sidebar', stylesheet)
        self.assertIn('[dir="ltr"] .dashboard-sidebar', stylesheet)
        self.assertIn("transform: translateX(105%);", stylesheet)
        self.assertIn("transform: translateX(-105%);", stylesheet)

    def test_dashboard_logout_is_language_correct_post_only_and_csrf_protected(self):
        response = self.dashboard(language="en")
        english_logout_url = reverse("patient_portal_logout_en")

        self.assertContains(
            response,
            f'<form class="dashboard-logout-form" method="post" action="{english_logout_url}">',
        )
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertEqual(self.client.get(english_logout_url).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(csrf_client.post(english_logout_url).status_code, 403)

        english_logout = self.client.post(english_logout_url)
        self.assertRedirects(english_logout, reverse("login_en"), fetch_redirect_response=False)

        arabic = self.dashboard(language="ar")
        arabic_logout_url = reverse("patient_portal_logout")
        self.assertContains(
            arabic,
            f'<form class="dashboard-logout-form" method="post" action="{arabic_logout_url}">',
        )
        arabic_logout = self.client.post(arabic_logout_url)
        self.assertRedirects(arabic_logout, reverse("login"), fetch_redirect_response=False)


class DashboardSchedulingTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.normal_user = self.create_user(username="synthetic-scheduling-non-staff")
        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب الجدولة التجريبي",
            full_name_en="Synthetic Scheduling Doctor",
            title_ar="د.",
            title_en="Dr.",
            is_active=True,
        )
        self.short_visit = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="خدمة قصيرة تجريبية",
            name_en="Synthetic short service",
            duration_minutes=15,
            is_active=True,
        )
        self.long_visit = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="خدمة طويلة تجريبية",
            name_en="Synthetic long service",
            duration_minutes=60,
            is_active=True,
        )
        self.set_booking_setting(SystemSetting.BOOKING_ENABLED, "true")
        self.set_booking_setting(SystemSetting.BOOKING_MIN_LEAD_MINUTES, "0")
        self.set_booking_setting(SystemSetting.BOOKING_MAX_DAYS_AHEAD, "30")
        self.set_booking_setting(SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES, "15")

    def set_booking_setting(self, key, value):
        SystemSetting.objects.update_or_create(
            key=key,
            defaults={"value": str(value)},
        )

    def scheduling_url(self, **params):
        route = reverse("dashboard_scheduling")
        if not params:
            return route
        return f"{route}?{urlencode(params)}"

    def scheduling(self, **params):
        return self.client.get(self.scheduling_url(**params))

    def future_date(self, offset=2):
        return timezone.localdate() + timedelta(days=offset)

    def create_schedule(self, day, start=time(9, 0), end=time(11, 0)):
        return DoctorSchedule.objects.create(
            doctor=self.doctor,
            weekday=day.weekday(),
            start_time=start,
            end_time=end,
            is_active=True,
        )

    def create_schedule_override(
        self,
        day,
        start=time(12, 0),
        end=time(15, 0),
        *,
        doctor=None,
        is_active=True,
        reason_ar="",
        reason_en="",
    ):
        return DoctorScheduleOverride.objects.create(
            doctor=doctor or self.doctor,
            date=day,
            start_time=start,
            end_time=end,
            is_active=is_active,
            reason_ar=reason_ar,
            reason_en=reason_en,
        )

    def aware_datetime(self, day, value):
        return timezone.make_aware(
            datetime.combine(day, value),
            timezone.get_current_timezone(),
        )

    def create_scheduling_appointment(
        self,
        day,
        *,
        start=time(9, 0),
        duration=30,
        patient_name="Synthetic Scheduling Patient",
        visit_type=None,
        doctor=None,
        **kwargs,
    ):
        patient = self.create_patient(full_name=patient_name)
        starts_at = self.aware_datetime(day, start)
        return Appointment.objects.create(
            doctor=doctor or self.doctor,
            patient=patient,
            visit_type=visit_type or self.short_visit,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=duration),
            **kwargs,
        )

    def assert_no_cache_headers(self, response):
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)

    def test_staff_access_boundary_get_only_and_never_cache(self):
        arabic_url = self.scheduling_url(view="day")
        arabic = self.client.get(arabic_url)
        self.assertEqual(arabic.status_code, 302)
        self.assertTrue(arabic["Location"].startswith(f"{reverse('login')}?role=doctor&next="))
        self.assertEqual(parse_qs(urlsplit(arabic["Location"]).query)["next"], [arabic_url])

        english_url = self.scheduling_url(lang="en", view="month")
        english = self.client.get(english_url)
        self.assertEqual(english.status_code, 302)
        self.assertTrue(english["Location"].startswith(f"{reverse('login_en')}?role=doctor&next="))
        self.assertEqual(parse_qs(urlsplit(english["Location"]).query)["next"], [english_url])

        self.client.force_login(self.normal_user)
        self.assertEqual(self.client.get(reverse("dashboard_scheduling")).status_code, 403)

        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard_scheduling"))
        self.assertEqual(response.status_code, 200)
        self.assert_no_cache_headers(response)
        post_response = self.client.post(reverse("dashboard_scheduling"), {"date": "2030-01-01"})
        self.assertEqual(post_response.status_code, 405)
        self.assert_no_cache_headers(post_response)

    def test_language_direction_labels_and_switch_preserve_context(self):
        self.client.force_login(self.staff)
        selected_date = self.future_date()
        arabic = self.scheduling(
            view="month",
            date=selected_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        self.assertContains(arabic, '<html lang="ar" dir="rtl">')
        self.assertContains(arabic, "مركز الجدولة")
        self.assertContains(arabic, "الجدولة")
        self.assertContains(arabic, "اليوم")
        self.assertContains(arabic, "الأسبوع")
        self.assertContains(arabic, "الشهر")
        switch_query = parse_qs(
            urlsplit(arabic.context["dashboard_language_switch_url"]).query
        )
        self.assertEqual(switch_query["lang"], ["en"])
        self.assertEqual(switch_query["view"], ["month"])
        self.assertEqual(switch_query["date"], [selected_date.isoformat()])
        self.assertEqual(switch_query["visit_type"], [str(self.short_visit.pk)])

        english = self.scheduling(
            lang="en",
            view="day",
            date=selected_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        self.assertContains(english, '<html lang="en" dir="ltr">')
        self.assertContains(english, "Scheduling Center")
        self.assertContains(english, "Working hours ≠ final availability")
        self.assertContains(english, "Synthetic short service")

    def test_view_date_and_visit_type_parameters_are_validated_safely(self):
        self.client.force_login(self.staff)
        selected_date = self.future_date()
        for view in ("day", "week", "month"):
            with self.subTest(view=view):
                response = self.scheduling(view=view, date=selected_date.isoformat())
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["scheduling_view"], view)
                self.assertEqual(response.context["scheduling_selected_date"], selected_date)

        invalid = self.scheduling(
            view="agenda",
            date="2026-02-31",
            visit_type="not-an-id",
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.context["scheduling_view"], "week")
        self.assertEqual(invalid.context["scheduling_selected_date"], timezone.localdate())
        self.assertIsNone(invalid.context["scheduling_selected_visit_type"])

        boundary_date = self.scheduling(view="week", date="9999-12-31")
        self.assertEqual(boundary_date.status_code, 200)
        self.assertEqual(
            boundary_date.context["scheduling_selected_date"],
            timezone.localdate(),
        )

        other_doctor = Doctor.objects.create(
            full_name_ar="طبيب آخر",
            full_name_en="Other doctor",
            is_active=True,
            display_order=20,
        )
        incompatible = VisitType.objects.create(
            doctor=other_doctor,
            name_ar="خدمة لطبيب آخر",
            name_en="Other doctor service",
            duration_minutes=30,
            is_active=True,
        )
        ignored = self.scheduling(visit_type=incompatible.pk)
        self.assertEqual(ignored.status_code, 200)
        self.assertIsNone(ignored.context["scheduling_selected_visit_type"])
        self.assertNotContains(ignored, incompatible.name_en)

        inactive = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="خدمة غير نشطة",
            name_en="Inactive service",
            duration_minutes=30,
            is_active=False,
        )
        ignored_inactive = self.scheduling(visit_type=inactive.pk)
        self.assertIsNone(ignored_inactive.context["scheduling_selected_visit_type"])

        clinic_wide = VisitType.objects.create(
            doctor=None,
            name_ar="خدمة عيادة عامة",
            name_en="Clinic-wide service",
            duration_minutes=30,
            is_active=True,
        )
        accepted_global = self.scheduling(visit_type=clinic_wide.pk)
        self.assertEqual(
            accepted_global.context["scheduling_selected_visit_type"],
            clinic_wide,
        )

    def test_no_active_doctor_renders_safe_bilingual_unavailable_state(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=["is_active"])
        self.client.force_login(self.staff)

        arabic = self.scheduling()
        english = self.scheduling(lang="en")

        self.assertEqual(arabic.status_code, 200)
        self.assertContains(arabic, "الجدولة غير متاحة حالياً")
        self.assertContains(english, "Scheduling is currently unavailable")
        self.assertEqual(english.context["scheduling_visit_types"], [])

    def test_multiple_working_periods_closed_day_and_no_schedule_states_render(self):
        selected_date = self.future_date()
        self.create_schedule(selected_date, time(9, 0), time(13, 0))
        self.create_schedule(selected_date, time(16, 0), time(19, 0))
        self.client.force_login(self.staff)

        response = self.scheduling(lang="en", view="day", date=selected_date.isoformat())
        periods = response.context["scheduling_selected_day"]["working_periods"]
        self.assertEqual(periods, [{"start": "09:00", "end": "13:00"}, {"start": "16:00", "end": "19:00"}])
        self.assertContains(response, "09:00")
        self.assertContains(response, "16:00")

        ClosedDay.objects.create(
            date=selected_date,
            doctor=self.doctor,
            reason_en="Synthetic doctor closure",
            reason_ar="إغلاق طبيب تجريبي",
            is_active=True,
        )
        ClosedDay.objects.create(
            date=selected_date,
            doctor=None,
            reason_en="Synthetic clinic closure",
            reason_ar="إغلاق عيادة تجريبي",
            is_active=True,
        )
        closed = self.scheduling(lang="en", view="day", date=selected_date.isoformat())
        self.assertTrue(closed.context["scheduling_selected_day"]["is_closed"])
        self.assertContains(closed, "Closed")
        self.assertContains(closed, "Synthetic doctor closure")
        self.assertContains(closed, "Synthetic clinic closure")

        DoctorSchedule.objects.all().delete()
        ClosedDay.objects.all().delete()
        no_schedule = self.scheduling(lang="en", view="day", date=selected_date.isoformat())
        self.assertContains(no_schedule, "No recurring working hours for this day.")

    def test_appointments_are_range_bounded_chronological_and_use_existing_detail_route(self):
        selected_date = self.future_date()
        late = self.create_scheduling_appointment(
            selected_date,
            start=time(11, 0),
            patient_name="Long English Scheduling Patient Name That Must Wrap Without Overflow",
        )
        early = self.create_scheduling_appointment(
            selected_date,
            start=time(9, 0),
            patient_name="اسم مريض عربي تجريبي طويل جداً لاختبار الالتفاف الآمن",
        )
        outside = self.create_scheduling_appointment(
            selected_date + timedelta(days=1),
            start=time(9, 0),
            patient_name="Outside visible day patient",
        )
        other_doctor = Doctor.objects.create(
            full_name_ar="طبيب نطاق آخر",
            full_name_en="Other range doctor",
            is_active=True,
            display_order=50,
        )
        other_visit = VisitType.objects.create(
            doctor=other_doctor,
            name_ar="زيارة أخرى",
            name_en="Other visit",
            duration_minutes=30,
        )
        other = self.create_scheduling_appointment(
            selected_date,
            start=time(10, 0),
            patient_name="Other doctor patient",
            doctor=other_doctor,
            visit_type=other_visit,
        )
        self.client.force_login(self.staff)

        response = self.scheduling(lang="en", view="day", date=selected_date.isoformat())
        appointment_items = response.context["scheduling_selected_day"]["appointments"]
        self.assertEqual(
            [item["patient_name"] for item in appointment_items],
            [early.patient.full_name, late.patient.full_name],
        )
        self.assertContains(response, early.patient.full_name)
        self.assertContains(response, late.patient.full_name)
        self.assertContains(
            response,
            reverse("staff_appointment_detail", kwargs={"appointment_id": early.pk}),
        )
        self.assertNotContains(response, outside.patient.full_name)
        self.assertNotContains(response, other.patient.full_name)

    def test_month_view_uses_counts_without_patient_names_and_one_bounded_joined_query(self):
        selected_date = self.future_date()
        appointment = self.create_scheduling_appointment(
            selected_date,
            patient_name="Month view hidden patient name",
        )
        self.client.force_login(self.staff)

        with CaptureQueriesContext(connection) as captured:
            response = self.scheduling(
                lang="en",
                view="month",
                date=selected_date.isoformat(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, appointment.patient.full_name)
        self.assertContains(response, "1 appt.")
        appointment_queries = [
            query["sql"]
            for query in captured.captured_queries
            if 'FROM "booking_appointment"' in query["sql"]
        ]
        self.assertEqual(len(appointment_queries), 1)
        self.assertIn('JOIN "patients_patient"', appointment_queries[0])
        self.assertIn('JOIN "clinic_doctor"', appointment_queries[0])
        self.assertIn('LEFT OUTER JOIN "clinic_visittype"', appointment_queries[0])

    def test_scheduling_response_omits_private_patient_and_record_data(self):
        selected_date = self.future_date()
        patient_user = self.create_user(username="scheduling-private-user")
        patient_user.email = "scheduling-private@example.test"
        patient_user.save(update_fields=["email"])
        patient = Patient.objects.create(
            user=patient_user,
            full_name="Scheduling Operational Name",
            phone_raw="0798888111",
            phone_e164="+962798888111",
            notes="SCHEDULING-PRIVATE-PATIENT-NOTES",
        )
        starts_at = self.aware_datetime(selected_date, time(9, 0))
        appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=patient,
            visit_type=self.short_visit,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            booking_note="SCHEDULING-PRIVATE-BOOKING-NOTE",
        )
        visit = self.create_visit(
            patient=patient,
            appointment=appointment,
            doctor_notes="SCHEDULING-PRIVATE-DOCTOR-NOTES",
            diagnosis_plan="SCHEDULING-PRIVATE-DIAGNOSIS",
        )
        self.create_note(
            patient=patient,
            visit=visit,
            body="SCHEDULING-PRIVATE-CLINICAL-NOTE",
        )
        media = self.create_media(
            patient=patient,
            title="SCHEDULING-PRIVATE-MEDIA",
        )
        self.client.force_login(self.staff)

        response = self.scheduling(view="day", date=selected_date.isoformat())
        self.assertContains(response, patient.full_name)
        for private_value in (
            patient.phone_raw,
            patient.phone_e164,
            patient_user.email,
            patient.notes,
            appointment.booking_note,
            str(appointment.public_token),
            visit.doctor_notes,
            visit.diagnosis_plan,
            "SCHEDULING-PRIVATE-CLINICAL-NOTE",
            media.title,
            str(media.public_id),
            media.file.name,
        ):
            self.assertNotContains(response, private_value)

    def test_selected_service_availability_reuses_booking_engine_for_schedule_collision_and_closure(self):
        selected_date = self.future_date()
        self.create_schedule(selected_date, time(9, 0), time(11, 0))
        self.client.force_login(self.staff)
        params = {
            "lang": "en",
            "view": "day",
            "date": selected_date.isoformat(),
            "visit_type": self.short_visit.pk,
        }

        with patch(
            "apps.dashboard.views.booking_services.generate_available_slots",
            wraps=booking_services.generate_available_slots,
        ) as generator:
            normal = self.scheduling(**params)
        self.assertEqual(generator.call_count, 1)
        self.assertTrue(normal.context["scheduling_selected_day"]["available_slots"])

        self.create_scheduling_appointment(
            selected_date,
            start=time(9, 0),
            duration=30,
            visit_type=self.short_visit,
        )
        collision = self.scheduling(**params)
        collision_starts = [
            slot["start"]
            for slot in collision.context["scheduling_selected_day"]["available_slots"]
        ]
        self.assertNotIn("09:00", collision_starts)
        self.assertNotIn("09:15", collision_starts)
        self.assertIn("09:30", collision_starts)

        ClosedDay.objects.create(
            doctor=self.doctor,
            date=selected_date,
            reason_en="Closed for controlled availability test",
        )
        closed = self.scheduling(**params)
        self.assertEqual(closed.context["scheduling_selected_day"]["available_slots"], [])

    def test_service_duration_minimum_lead_and_horizon_change_real_availability(self):
        selected_date = self.future_date()
        self.create_schedule(selected_date, time(9, 0), time(10, 0))
        self.client.force_login(self.staff)

        short = self.scheduling(
            view="day",
            date=selected_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        long = self.scheduling(
            view="day",
            date=selected_date.isoformat(),
            visit_type=self.long_visit.pk,
        )
        self.assertEqual(len(short.context["scheduling_selected_day"]["available_slots"]), 4)
        self.assertEqual(len(long.context["scheduling_selected_day"]["available_slots"]), 1)

        self.set_booking_setting(SystemSetting.BOOKING_MIN_LEAD_MINUTES, "4320")
        lead_limited = self.scheduling(
            view="day",
            date=selected_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        self.assertEqual(lead_limited.context["scheduling_selected_day"]["available_slots"], [])

        self.set_booking_setting(SystemSetting.BOOKING_MIN_LEAD_MINUTES, "0")
        self.set_booking_setting(SystemSetting.BOOKING_MAX_DAYS_AHEAD, "1")
        horizon_limited = self.scheduling(
            view="day",
            date=selected_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        self.assertEqual(horizon_limited.context["scheduling_selected_day"]["available_slots"], [])

    def test_availability_call_count_is_zero_for_all_services_and_bounded_by_view(self):
        selected_date = self.future_date()
        for offset in range(7):
            day = selected_date - timedelta(days=selected_date.weekday()) + timedelta(days=offset)
            self.create_schedule(day, time(9, 0), time(10, 0))
        self.client.force_login(self.staff)

        with patch(
            "apps.dashboard.views.booking_services.generate_available_slots",
            wraps=booking_services.generate_available_slots,
        ) as generator:
            self.scheduling(view="week", date=selected_date.isoformat())
            self.assertEqual(generator.call_count, 0)

        for view, expected_calls in (("day", 1), ("week", 7), ("month", 1)):
            with self.subTest(view=view), patch(
                "apps.dashboard.views.booking_services.generate_available_slots",
                wraps=booking_services.generate_available_slots,
            ) as generator:
                response = self.scheduling(
                    view=view,
                    date=selected_date.isoformat(),
                    visit_type=self.short_visit.pk,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(generator.call_count, expected_calls)

    def test_navigation_preserves_context_and_mobile_progressive_default_is_safe(self):
        selected_date = self.future_date()
        self.client.force_login(self.staff)
        response = self.scheduling(
            lang="en",
            view="week",
            date=selected_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        for context_key in (
            "scheduling_previous_url",
            "scheduling_today_url",
            "scheduling_next_url",
        ):
            query = parse_qs(urlsplit(response.context[context_key]).query)
            self.assertEqual(query["lang"], ["en"])
            self.assertEqual(query["view"], ["week"])
            self.assertEqual(query["visit_type"], [str(self.short_visit.pk)])

        project_root = Path(__file__).resolve().parents[2]
        javascript = (project_root / "static" / "js" / "dashboard-scheduling.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('searchParams.has("view")', javascript)
        self.assertIn('matchMedia("(max-width: 35rem)")', javascript)
        self.assertIn('searchParams.set("view", "day")', javascript)
        self.assertIn("window.location.replace", javascript)

    def test_calendar_keeps_operational_scope_while_exposing_special_hours(self):
        self.client.force_login(self.staff)
        response = self.scheduling(lang="en")

        self.assertContains(response, "Effective hours")
        self.assertContains(response, "Special hours for this date")
        for prohibited_label in (
            "Close Day",
            "Edit Hours",
            "Save Schedule",
            "Drag",
            "Medical Records",
            "Clinic Settings",
            "Content",
            "Reviews",
        ):
            self.assertNotContains(response, prohibited_label)

    def rules_payload(self, **overrides):
        payload = {
            "booking_enabled": "true",
            "booking_min_lead_minutes": "0",
            "booking_max_days_ahead": "30",
            "booking_slot_interval_minutes": "15",
            "appointment_reminder_offset_minutes": "180",
        }
        payload.update(overrides)
        return payload

    def action_url(self, name, *, language=None, **kwargs):
        url = reverse(name, kwargs=kwargs or None)
        return f"{url}?lang=en" if language == "en" else url

    def special_action_url(self, name, day, *, language="en", **kwargs):
        url = self.action_url(name, language=language, **kwargs)
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}{urlencode({'view': 'day', 'date': day.isoformat()})}"

    def test_management_sections_are_allowlisted_bilingual_and_keep_calendar_default(self):
        self.client.force_login(self.staff)
        response = self.scheduling(lang="en", section="weekly")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["scheduling_section"], "weekly")
        self.assertEqual(len(response.context["scheduling_weekly_days"]), 7)
        for label in ("Calendar", "Weekly Hours", "Services", "Booking Rules", "Closures"):
            self.assertContains(response, label)
        self.assertContains(response, 'dir="ltr"')
        self.assertNotContains(response, "Special Hours")

        arabic = self.scheduling(section="closures")
        for label in ("التقويم", "ساعات العمل الأسبوعية", "الخدمات", "قواعد الحجز", "الإغلاقات"):
            self.assertContains(arabic, label)
        self.assertContains(arabic, 'dir="rtl"')

        invalid = self.scheduling(section="not-a-real-section")
        self.assertEqual(invalid.context["scheduling_section"], "calendar")
        self.assertContains(invalid, "الساعات الفعالة")

    def test_special_hours_create_validation_overlap_audit_and_booking_effect(self):
        target_date = self.future_date(8)
        self.create_schedule(target_date, time(9), time(17))
        inactive = self.create_schedule_override(
            target_date,
            time(12),
            time(15),
            is_active=False,
        )
        create_url = self.special_action_url(
            "dashboard_scheduling_special_create",
            target_date,
        )
        self.client.force_login(self.staff)

        for start_value, end_value in (
            ("not-a-time", "15:00"),
            ("12:00", "12:00"),
            ("15:00", "12:00"),
        ):
            with self.subTest(start=start_value, end=end_value):
                response = self.client.post(
                    create_url,
                    {
                        "date": target_date.isoformat(),
                        "start_time": start_value,
                        "end_time": end_value,
                        "reason_ar": "",
                        "reason_en": "",
                    },
                )
                self.assertEqual(response.status_code, 400)

        first_payload = {
            "date": target_date.isoformat(),
            "start_time": "12:00",
            "end_time": "15:00",
            "reason_ar": "دوام خاص تجريبي",
            "reason_en": "Synthetic Special Hours",
        }
        created = self.client.post(create_url, first_payload)
        self.assertEqual(created.status_code, 302)
        redirect_query = parse_qs(urlsplit(created["Location"]).query)
        self.assertEqual(redirect_query["lang"], ["en"])
        self.assertEqual(redirect_query["view"], ["day"])
        self.assertEqual(redirect_query["date"], [target_date.isoformat()])
        first = DoctorScheduleOverride.objects.get(
            doctor=self.doctor,
            date=target_date,
            start_time=time(12),
            is_active=True,
        )
        self.assertFalse(inactive.is_active)

        second = self.client.post(
            create_url,
            {
                "date": target_date.isoformat(),
                "start_time": "16:00",
                "end_time": "18:00",
                "reason_ar": "",
                "reason_en": "Second period",
            },
        )
        self.assertEqual(second.status_code, 302)
        overlap = self.client.post(
            create_url,
            {
                "date": target_date.isoformat(),
                "start_time": "14:30",
                "end_time": "16:30",
                "reason_ar": "",
                "reason_en": "Overlap",
            },
        )
        self.assertEqual(overlap.status_code, 400)
        self.assertContains(overlap, "overlaps", status_code=400)
        self.assertEqual(
            DoctorScheduleOverride.objects.filter(
                doctor=self.doctor,
                date=target_date,
                is_active=True,
            ).count(),
            2,
        )

        slots = booking_services.generate_available_slots(
            self.short_visit,
            target_date=target_date,
            doctor=self.doctor,
        )
        slot_times = [slot.local_time.strftime("%H:%M") for slot in slots]
        self.assertEqual(slot_times[0], "12:00")
        self.assertIn("16:00", slot_times)
        self.assertNotIn("09:00", slot_times)
        audit = AuditLog.objects.get(
            action=AuditLog.Action.CREATE,
            model_name="DoctorScheduleOverride",
            object_id=str(first.pk),
        )
        self.assertEqual(audit.metadata["date"], target_date.isoformat())
        self.assertEqual(audit.metadata["new_start"], "12:00")
        self.assertNotIn("patient", str(audit.metadata).lower())

    def test_special_hours_update_excludes_self_locks_date_and_enforces_doctor(self):
        target_date = self.future_date(9)
        first = self.create_schedule_override(target_date, time(9), time(12))
        self.create_schedule_override(target_date, time(16), time(18))
        update_url = self.special_action_url(
            "dashboard_scheduling_special_update",
            target_date,
            period_id=first.pk,
        )
        self.client.force_login(self.staff)
        payload = {
            "date": target_date.isoformat(),
            "start_time": "10:00",
            "end_time": "13:00",
            "reason_ar": "سبب محدث",
            "reason_en": "Updated reason",
        }

        updated = self.client.post(update_url, payload)
        self.assertEqual(updated.status_code, 302)
        first.refresh_from_db()
        self.assertEqual((first.start_time, first.end_time), (time(10), time(13)))
        self.assertEqual(first.reason_en, "Updated reason")
        audit = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE,
            model_name="DoctorScheduleOverride",
            object_id=str(first.pk),
        ).latest("created_at")
        self.assertEqual(audit.metadata["old_start"], "09:00")
        self.assertEqual(audit.metadata["new_start"], "10:00")

        overlap = self.client.post(
            update_url,
            {**payload, "start_time": "17:00", "end_time": "19:00"},
        )
        self.assertEqual(overlap.status_code, 400)
        tampered_date = self.client.post(
            update_url,
            {**payload, "date": (target_date + timedelta(days=1)).isoformat()},
        )
        self.assertEqual(tampered_date.status_code, 400)
        first.refresh_from_db()
        self.assertEqual((first.date, first.start_time), (target_date, time(10)))

        other_doctor = Doctor.objects.create(
            full_name_ar="طبيب ساعات خاصة آخر",
            full_name_en="Other Special Hours doctor",
            is_active=True,
            display_order=20,
        )
        other = self.create_schedule_override(
            target_date,
            time(14),
            time(15),
            doctor=other_doctor,
        )
        wrong_doctor = self.client.post(
            self.special_action_url(
                "dashboard_scheduling_special_update",
                target_date,
                period_id=other.pk,
            ),
            {
                "date": target_date.isoformat(),
                "start_time": "15:00",
                "end_time": "16:00",
                "reason_ar": "",
                "reason_en": "",
            },
        )
        self.assertEqual(wrong_doctor.status_code, 404)
        other.refresh_from_db()
        self.assertEqual(other.start_time, time(14))

    def test_special_hours_conflict_confirmation_requeries_and_preserves_private_appointments(self):
        target_date = self.future_date(10)
        appointment = self.create_scheduling_appointment(
            target_date,
            start=time(10),
            duration=30,
            patient_name="Visible Special Conflict Name",
            status=Appointment.Status.CONFIRMED,
            booking_note="SPECIAL-PRIVATE-BOOKING-NOTE",
        )
        appointment.patient.phone_raw = "+962799999992"
        appointment.patient.phone_e164 = "+962799999992"
        appointment.patient.save(update_fields=["phone_raw", "phone_e164"])
        original_status = appointment.status
        create_url = self.special_action_url(
            "dashboard_scheduling_special_create",
            target_date,
        )
        payload = {
            "date": target_date.isoformat(),
            "start_time": "12:00",
            "end_time": "15:00",
            "reason_ar": "",
            "reason_en": "Conflict-confirmed Special Hours",
        }
        self.client.force_login(self.staff)

        with patch(
            "apps.dashboard.views._special_hours_conflicts",
            wraps=dashboard_views._special_hours_conflicts,
        ) as conflict_query:
            warning = self.client.post(create_url, payload)
            self.assertEqual(warning.status_code, 200)
            self.assertContains(warning, "Existing appointments fall outside the proposed effective hours")
            self.assertContains(warning, "Visible Special Conflict Name")
            self.assertContains(warning, "10:00–10:30")
            self.assertFalse(
                DoctorScheduleOverride.objects.filter(
                    doctor=self.doctor,
                    date=target_date,
                    is_active=True,
                ).exists()
            )
            for private_value in (
                "+962799999992",
                "SPECIAL-PRIVATE-BOOKING-NOTE",
                str(appointment.public_token),
                "private-media",
            ):
                self.assertNotContains(warning, private_value)

            second = self.create_scheduling_appointment(
                target_date,
                start=time(14, 30),
                duration=60,
                patient_name="Requeried Boundary Conflict",
                status=Appointment.Status.ARRIVED,
            )
            confirmed = self.client.post(
                create_url,
                {**payload, "confirm_special_hours": "yes"},
            )
            self.assertEqual(confirmed.status_code, 302)
            self.assertEqual(conflict_query.call_count, 2)

        override = DoctorScheduleOverride.objects.get(
            doctor=self.doctor,
            date=target_date,
            is_active=True,
        )
        appointment.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(appointment.status, original_status)
        self.assertEqual(second.status, Appointment.Status.ARRIVED)
        self.assertTrue(Appointment.objects.filter(pk=appointment.pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=second.pk).exists())
        audit = AuditLog.objects.get(
            action=AuditLog.Action.CREATE,
            model_name="DoctorScheduleOverride",
            object_id=str(override.pk),
        )
        metadata_text = str(audit.metadata)
        self.assertNotIn("Visible Special Conflict Name", metadata_text)
        self.assertNotIn("Requeried Boundary Conflict", metadata_text)
        self.assertNotIn("SPECIAL-PRIVATE", metadata_text)

    def test_special_hours_conflicts_require_whole_interval_containment(self):
        target_date = self.future_date(11)
        first = self.create_schedule_override(target_date, time(9), time(12))
        self.create_schedule_override(target_date, time(16), time(18))
        noon_conflict = self.create_scheduling_appointment(
            target_date,
            start=time(11, 30),
            duration=60,
            patient_name="Crosses Noon Boundary",
        )
        afternoon_conflict = self.create_scheduling_appointment(
            target_date,
            start=time(15, 30),
            duration=60,
            patient_name="Crosses Afternoon Boundary",
        )
        compatible = self.create_scheduling_appointment(
            target_date,
            start=time(16, 15),
            duration=45,
            patient_name="Wholly Compatible Appointment",
        )
        self.client.force_login(self.staff)

        update_url = self.special_action_url(
            "dashboard_scheduling_special_update",
            target_date,
            period_id=first.pk,
        )
        payload = {
            "date": target_date.isoformat(),
            "start_time": "09:00",
            "end_time": "12:00",
            "reason_ar": "",
            "reason_en": "Confirmed containment update",
        }
        warning = self.client.post(
            update_url,
            payload,
        )

        self.assertEqual(warning.status_code, 200)
        conflicts = warning.context["scheduling_special_conflicts"]
        self.assertEqual(
            {item["patient_name"] for item in conflicts},
            {"Crosses Noon Boundary", "Crosses Afternoon Boundary"},
        )
        first.refresh_from_db()
        self.assertTrue(first.is_active)
        self.assertEqual(first.reason_en, "")

        confirmed = self.client.post(
            update_url,
            {**payload, "confirm_special_hours": "yes"},
        )
        self.assertEqual(confirmed.status_code, 302)
        first.refresh_from_db()
        self.assertEqual(first.reason_en, "Confirmed containment update")
        for appointment in (noon_conflict, afternoon_conflict, compatible):
            appointment.refresh_from_db()
            self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)

    def test_special_hours_deactivate_and_use_weekly_validate_final_schedule(self):
        target_date = self.future_date(12)
        self.create_schedule(target_date, time(9), time(12))
        period = self.create_schedule_override(target_date, time(9), time(17))
        second_period = self.create_schedule_override(target_date, time(18), time(19))
        appointment = self.create_scheduling_appointment(
            target_date,
            start=time(16),
            duration=30,
            patient_name="Weekly Reduction Conflict",
        )
        use_weekly_url = self.special_action_url(
            "dashboard_scheduling_special_use_weekly",
            target_date,
        )
        self.client.force_login(self.staff)

        warning = self.client.post(use_weekly_url, {"date": target_date.isoformat()})
        self.assertEqual(warning.status_code, 200)
        self.assertContains(warning, "Weekly Reduction Conflict")
        period.refresh_from_db()
        self.assertTrue(period.is_active)
        confirmed = self.client.post(
            use_weekly_url,
            {"date": target_date.isoformat(), "confirm_special_hours": "yes"},
        )
        self.assertEqual(confirmed.status_code, 302)
        period.refresh_from_db()
        second_period.refresh_from_db()
        appointment.refresh_from_db()
        self.assertFalse(period.is_active)
        self.assertFalse(second_period.is_active)
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        audit = AuditLog.objects.filter(
            model_name="DoctorScheduleOverride",
            object_id=str(period.pk),
        ).latest("created_at")
        self.assertEqual(audit.metadata["operation"], "use_weekly_schedule")

        expanding_date = self.future_date(13)
        self.create_schedule(expanding_date, time(9), time(17))
        expanding = self.create_schedule_override(
            expanding_date,
            time(12),
            time(15),
        )
        no_warning = self.client.post(
            self.special_action_url(
                "dashboard_scheduling_special_use_weekly",
                expanding_date,
            ),
            {"date": expanding_date.isoformat()},
        )
        self.assertEqual(no_warning.status_code, 302)
        expanding.refresh_from_db()
        self.assertFalse(expanding.is_active)

    def test_deactivating_one_special_period_checks_remaining_effective_periods(self):
        target_date = self.future_date(14)
        first = self.create_schedule_override(target_date, time(9), time(12))
        self.create_schedule_override(target_date, time(16), time(18))
        appointment = self.create_scheduling_appointment(
            target_date,
            start=time(9, 30),
            duration=30,
            patient_name="Deactivation Conflict",
        )
        url = self.special_action_url(
            "dashboard_scheduling_special_deactivate",
            target_date,
            period_id=first.pk,
        )
        self.client.force_login(self.staff)

        warning = self.client.post(url)
        self.assertEqual(warning.status_code, 200)
        self.assertContains(warning, "Deactivation Conflict")
        first.refresh_from_db()
        self.assertTrue(first.is_active)
        confirmed = self.client.post(url, {"confirm_special_hours": "yes"})
        self.assertEqual(confirmed.status_code, 302)
        first.refresh_from_db()
        appointment.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        audit = AuditLog.objects.filter(
            model_name="DoctorScheduleOverride",
            object_id=str(first.pk),
        ).latest("created_at")
        self.assertEqual(audit.metadata["operation"], "deactivate")
        self.assertFalse(audit.metadata["active"])

    def test_calendar_uses_effective_source_for_day_week_month_and_inspector(self):
        target_date = self.future_date(15)
        self.create_schedule(target_date, time(9), time(17))
        self.create_schedule_override(
            target_date,
            time(12),
            time(15),
            reason_en="Exact-date reduced hours",
        )
        self.client.force_login(self.staff)

        day = self.scheduling(
            lang="en",
            view="day",
            date=target_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        selected = day.context["scheduling_selected_day"]
        self.assertEqual(selected["effective_source"], booking_services.WORKING_PERIOD_SOURCE_SPECIAL)
        self.assertEqual(selected["weekly_periods"], [{"start": "09:00", "end": "17:00"}])
        self.assertEqual(selected["special_periods"], [{"start": "12:00", "end": "15:00"}])
        self.assertEqual(selected["working_periods"], selected["special_periods"])
        production_slots = booking_services.generate_available_slots(
            self.short_visit,
            target_date=target_date,
            doctor=self.doctor,
        )
        self.assertEqual(
            [item["start"] for item in selected["available_slots"]],
            [slot.local_time.strftime("%H:%M") for slot in production_slots],
        )
        self.assertContains(day, "Effective source")
        self.assertContains(day, "Special hours")

        week = self.scheduling(lang="en", view="week", date=target_date.isoformat())
        week_day = next(item for item in week.context["scheduling_days"] if item["date"] == target_date)
        self.assertEqual(week_day["working_periods"], [{"start": "12:00", "end": "15:00"}])
        self.assertContains(week, "Special hours")

        neighboring_date = target_date + timedelta(days=7)
        neighbor = self.scheduling(lang="en", view="day", date=neighboring_date.isoformat())
        self.assertEqual(
            neighbor.context["scheduling_selected_day"]["effective_source"],
            booking_services.WORKING_PERIOD_SOURCE_WEEKLY,
        )
        self.assertEqual(
            neighbor.context["scheduling_selected_day"]["working_periods"],
            [{"start": "09:00", "end": "17:00"}],
        )

        month = self.scheduling(
            lang="en",
            view="month",
            date=target_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        month_day = next(item for item in month.context["scheduling_days"] if item["date"] == target_date)
        self.assertTrue(month_day["has_special_hours"])
        self.assertContains(month, ">Special<")
        action_query = parse_qs(
            urlsplit(month.context["scheduling_special_create_url"]).query
        )
        self.assertEqual(action_query["lang"], ["en"])
        self.assertEqual(action_query["view"], ["month"])
        self.assertEqual(action_query["date"], [target_date.isoformat()])
        self.assertEqual(action_query["visit_type"], [str(self.short_visit.pk)])
        preserved_redirect = self.client.post(
            month.context["scheduling_special_create_url"],
            {
                "date": target_date.isoformat(),
                "start_time": "15:00",
                "end_time": "16:00",
                "reason_ar": "",
                "reason_en": "Preserve management state",
            },
        )
        preserved_query = parse_qs(urlsplit(preserved_redirect["Location"]).query)
        self.assertEqual(preserved_query["section"], ["calendar"])
        self.assertEqual(preserved_query["view"], ["month"])
        self.assertEqual(preserved_query["date"], [target_date.isoformat()])
        self.assertEqual(preserved_query["visit_type"], [str(self.short_visit.pk)])

        ClosedDay.objects.create(doctor=self.doctor, date=target_date, is_active=True)
        closed = self.scheduling(lang="en", view="day", date=target_date.isoformat())
        closed_day = closed.context["scheduling_selected_day"]
        self.assertEqual(closed_day["effective_source"], booking_services.WORKING_PERIOD_SOURCE_CLOSED)
        self.assertEqual(closed_day["working_periods"], [])
        self.assertTrue(closed_day["special_periods"])
        self.assertContains(
            closed,
            "This date is closed. Special hours are preserved but ignored while the closure is active.",
            count=2,
        )

    def test_weekly_period_create_validation_deactivation_audit_and_real_availability(self):
        target_date = self.future_date(3)
        weekday = target_date.weekday()
        create_url = self.action_url("dashboard_scheduling_weekly_create", language="en")
        self.client.force_login(self.staff)

        malformed = self.client.post(
            create_url,
            {"weekday": weekday, "start_time": "not-a-time", "end_time": "11:00"},
        )
        self.assertEqual(malformed.status_code, 400)
        equal = self.client.post(
            create_url,
            {"weekday": weekday, "start_time": "09:00", "end_time": "09:00"},
        )
        self.assertEqual(equal.status_code, 400)
        reversed_time = self.client.post(
            create_url,
            {"weekday": weekday, "start_time": "11:00", "end_time": "09:00"},
        )
        self.assertEqual(reversed_time.status_code, 400)
        self.assertFalse(DoctorSchedule.objects.filter(doctor=self.doctor, weekday=weekday).exists())

        first = self.client.post(
            create_url,
            {"weekday": weekday, "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertEqual(first.status_code, 302)
        self.assertEqual(parse_qs(urlsplit(first["Location"]).query)["section"], ["weekly"])
        self.assertEqual(parse_qs(urlsplit(first["Location"]).query)["lang"], ["en"])
        period = DoctorSchedule.objects.get(
            doctor=self.doctor,
            weekday=weekday,
            start_time=time(9, 0),
        )
        create_audit = AuditLog.objects.get(
            action=AuditLog.Action.CREATE,
            model_name="DoctorSchedule",
            object_id=str(period.pk),
        )
        self.assertEqual(create_audit.metadata["weekday"], weekday)
        self.assertEqual(create_audit.metadata["new_start"], "09:00")

        second = self.client.post(
            create_url,
            {"weekday": weekday, "start_time": "12:00", "end_time": "13:00"},
        )
        self.assertEqual(second.status_code, 302)
        overlapping = self.client.post(
            create_url,
            {"weekday": weekday, "start_time": "09:30", "end_time": "12:30"},
        )
        self.assertEqual(overlapping.status_code, 400)
        self.assertContains(overlapping, "overlaps an active working period", status_code=400)
        self.assertEqual(
            DoctorSchedule.objects.filter(doctor=self.doctor, weekday=weekday, is_active=True).count(),
            2,
        )

        available = booking_services.generate_available_slots(
            self.short_visit,
            target_date=target_date,
            doctor=self.doctor,
        )
        self.assertTrue(available)
        deactivate = self.client.post(
            self.action_url(
                "dashboard_scheduling_weekly_deactivate",
                language="en",
                period_id=period.pk,
            )
        )
        self.assertEqual(deactivate.status_code, 302)
        period.refresh_from_db()
        self.assertFalse(period.is_active)
        deactivate_audit = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE,
            model_name="DoctorSchedule",
            object_id=str(period.pk),
        ).latest("created_at")
        self.assertFalse(deactivate_audit.metadata["active"])

        DoctorSchedule.objects.filter(
            doctor=self.doctor,
            weekday=weekday,
            start_time=time(12, 0),
        ).update(is_active=False)
        self.assertEqual(
            booking_services.generate_available_slots(
                self.short_visit,
                target_date=target_date,
                doctor=self.doctor,
            ),
            [],
        )

        inactive_weekday = (weekday + 1) % 7
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            weekday=inactive_weekday,
            start_time=time(8, 0),
            end_time=time(10, 0),
            is_active=False,
        )
        inactive_does_not_block = self.client.post(
            create_url,
            {"weekday": inactive_weekday, "start_time": "08:30", "end_time": "09:30"},
        )
        self.assertEqual(inactive_does_not_block.status_code, 302)

    def test_weekly_update_excludes_itself_rejects_other_overlap_and_enforces_active_doctor(self):
        period = DoctorSchedule.objects.create(
            doctor=self.doctor,
            weekday=DoctorSchedule.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        DoctorSchedule.objects.create(
            doctor=self.doctor,
            weekday=DoctorSchedule.Weekday.MONDAY,
            start_time=time(13, 0),
            end_time=time(15, 0),
        )
        self.client.force_login(self.staff)
        update_url = self.action_url(
            "dashboard_scheduling_weekly_update",
            language="en",
            period_id=period.pk,
        )
        self.assertEqual(
            self.client.post(update_url, {"start_time": "09:00", "end_time": "11:00"}).status_code,
            302,
        )
        update_audit = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE,
            model_name="DoctorSchedule",
            object_id=str(period.pk),
        ).latest("created_at")
        self.assertTrue(update_audit.metadata["active"])
        self.assertEqual(update_audit.metadata["old_start"], "09:00")
        self.assertEqual(update_audit.metadata["new_end"], "11:00")
        overlap = self.client.post(
            update_url,
            {"start_time": "12:30", "end_time": "14:00"},
        )
        self.assertEqual(overlap.status_code, 400)
        period.refresh_from_db()
        self.assertEqual((period.start_time, period.end_time), (time(9, 0), time(11, 0)))

        other_doctor = Doctor.objects.create(
            full_name_ar="طبيب آخر",
            full_name_en="Other synthetic doctor",
            is_active=True,
            display_order=10,
        )
        other_period = DoctorSchedule.objects.create(
            doctor=other_doctor,
            weekday=DoctorSchedule.Weekday.TUESDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        wrong_doctor = self.client.post(
            self.action_url(
                "dashboard_scheduling_weekly_update",
                period_id=other_period.pk,
            ),
            {"start_time": "10:00", "end_time": "11:00"},
        )
        self.assertEqual(wrong_doctor.status_code, 404)
        other_period.refresh_from_db()
        self.assertEqual(other_period.start_time, time(9, 0))

    def test_closure_create_deactivate_audit_and_booking_engine_effect(self):
        target_date = self.future_date(4)
        self.create_schedule(target_date, time(9, 0), time(10, 0))
        self.client.force_login(self.staff)
        before = booking_services.generate_available_slots(
            self.short_visit,
            target_date=target_date,
            doctor=self.doctor,
        )
        self.assertTrue(before)

        created = self.client.post(
            self.action_url("dashboard_scheduling_closure_create", language="en"),
            {
                "date": target_date.isoformat(),
                "reason_ar": "إغلاق تجريبي",
                "reason_en": "Synthetic closure",
            },
        )
        self.assertEqual(created.status_code, 302)
        closure = ClosedDay.objects.get(doctor=self.doctor, date=target_date, is_active=True)
        self.assertEqual(
            booking_services.generate_available_slots(
                self.short_visit,
                target_date=target_date,
                doctor=self.doctor,
            ),
            [],
        )
        create_audit = AuditLog.objects.get(
            action=AuditLog.Action.CREATE,
            model_name="ClosedDay",
            object_id=str(closure.pk),
        )
        self.assertEqual(create_audit.metadata["date"], target_date.isoformat())
        self.assertNotIn("patient", str(create_audit.metadata).lower())

        deactivated = self.client.post(
            self.action_url(
                "dashboard_scheduling_closure_deactivate",
                language="en",
                closure_id=closure.pk,
            )
        )
        self.assertEqual(deactivated.status_code, 302)
        closure.refresh_from_db()
        self.assertFalse(closure.is_active)
        self.assertTrue(
            booking_services.generate_available_slots(
                self.short_visit,
                target_date=target_date,
                doctor=self.doctor,
            )
        )
        audit = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE,
            model_name="ClosedDay",
            object_id=str(closure.pk),
        ).latest("created_at")
        self.assertFalse(audit.metadata["active"])

    def test_closure_conflict_requires_confirmation_requeries_and_keeps_appointments_private_intact(self):
        target_date = self.future_date(5)
        appointment = self.create_scheduling_appointment(
            target_date,
            patient_name="Allowed Conflict Summary Name",
            status=Appointment.Status.CONFIRMED,
            booking_note="SENSITIVE-BOOKING-NOTE-NEVER-RENDER",
        )
        appointment.patient.phone_raw = "+962799999991"
        appointment.patient.phone_e164 = "+962799999991"
        appointment.patient.save(update_fields=["phone_raw", "phone_e164"])
        original_status = appointment.status
        create_url = self.action_url("dashboard_scheduling_closure_create", language="en")
        payload = {
            "date": target_date.isoformat(),
            "reason_ar": "",
            "reason_en": "Conflict-confirmed closure",
        }
        self.client.force_login(self.staff)

        with patch(
            "apps.dashboard.views._closure_conflict_queryset",
            wraps=dashboard_views._closure_conflict_queryset,
        ) as conflict_query:
            warning = self.client.post(create_url, payload)
            self.assertEqual(warning.status_code, 200)
            self.assertContains(warning, "Existing appointments conflict with closing this day")
            self.assertContains(warning, "Allowed Conflict Summary Name")
            self.assertContains(warning, "Synthetic short service")
            self.assertContains(warning, "Confirmed")
            self.assertFalse(ClosedDay.objects.filter(doctor=self.doctor, date=target_date).exists())
            for private_value in (
                "+962799999991",
                "SENSITIVE-BOOKING-NOTE-NEVER-RENDER",
                str(appointment.public_token),
                "diagnosis",
                "private-media",
            ):
                self.assertNotContains(warning, private_value)

            second_conflict = self.create_scheduling_appointment(
                target_date,
                start=time(10, 0),
                patient_name="Second Requeried Conflict",
                status=Appointment.Status.ARRIVED,
            )
            confirmed = self.client.post(
                create_url,
                {**payload, "confirm_closure": "yes"},
            )
            self.assertEqual(confirmed.status_code, 302)
            self.assertEqual(conflict_query.call_count, 2)

        closure = ClosedDay.objects.get(doctor=self.doctor, date=target_date, is_active=True)
        appointment.refresh_from_db()
        second_conflict.refresh_from_db()
        self.assertEqual(appointment.status, original_status)
        self.assertEqual(second_conflict.status, Appointment.Status.ARRIVED)
        self.assertTrue(Appointment.objects.filter(pk=appointment.pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=second_conflict.pk).exists())
        audit = AuditLog.objects.get(
            action=AuditLog.Action.CREATE,
            model_name="ClosedDay",
            object_id=str(closure.pk),
        )
        metadata_text = str(audit.metadata)
        self.assertNotIn("Allowed Conflict Summary Name", metadata_text)
        self.assertNotIn("Second Requeried Conflict", metadata_text)
        self.assertNotIn("SENSITIVE", metadata_text)

    def test_nonblocking_appointment_does_not_trigger_closure_confirmation(self):
        target_date = self.future_date(6)
        appointment = self.create_scheduling_appointment(
            target_date,
            status=Appointment.Status.CANCELLED,
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            self.action_url("dashboard_scheduling_closure_create", language="en"),
            {"date": target_date.isoformat(), "reason_ar": "", "reason_en": "No conflict"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ClosedDay.objects.filter(doctor=self.doctor, date=target_date).exists())
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)

    def test_service_duration_only_update_validation_audit_and_availability(self):
        target_date = self.future_date(3)
        self.create_schedule(target_date, time(9, 0), time(10, 0))
        self.short_visit.price = "45.00"
        self.short_visit.show_price_to_patient = True
        self.short_visit.instructions_en = "Unchanged service instructions"
        self.short_visit.display_order = 7
        self.short_visit.save()
        self.short_visit.refresh_from_db()
        unchanged = {
            "doctor_id": self.short_visit.doctor_id,
            "name_ar": self.short_visit.name_ar,
            "name_en": self.short_visit.name_en,
            "price": self.short_visit.price,
            "show_price_to_patient": self.short_visit.show_price_to_patient,
            "instructions_en": self.short_visit.instructions_en,
            "display_order": self.short_visit.display_order,
            "is_active": self.short_visit.is_active,
        }
        update_url = self.action_url(
            "dashboard_scheduling_service_duration",
            language="en",
            visit_type_id=self.short_visit.pk,
        )
        self.client.force_login(self.staff)
        for invalid in ("0", "-1", "not-an-integer"):
            with self.subTest(invalid=invalid):
                response = self.client.post(update_url, {"duration_minutes": invalid})
                self.assertEqual(response.status_code, 400)
        self.short_visit.refresh_from_db()
        self.assertEqual(self.short_visit.duration_minutes, 15)
        self.assertEqual(
            len(
                booking_services.generate_available_slots(
                    self.short_visit,
                    target_date=target_date,
                    doctor=self.doctor,
                )
            ),
            4,
        )

        updated = self.client.post(update_url, {"duration_minutes": "60"})
        self.assertEqual(updated.status_code, 302)
        self.short_visit.refresh_from_db()
        self.assertEqual(self.short_visit.duration_minutes, 60)
        for field_name, value in unchanged.items():
            self.assertEqual(getattr(self.short_visit, field_name), value)
        self.assertEqual(
            len(
                booking_services.generate_available_slots(
                    self.short_visit,
                    target_date=target_date,
                    doctor=self.doctor,
                )
            ),
            1,
        )
        audit = AuditLog.objects.get(
            action=AuditLog.Action.UPDATE,
            model_name="VisitType",
            object_id=str(self.short_visit.pk),
        )
        self.assertEqual(audit.metadata["old_duration_minutes"], 15)
        self.assertEqual(audit.metadata["new_duration_minutes"], 60)

    def test_booking_rules_update_existing_and_missing_rows_validation_types_and_audit(self):
        reminder_key = SystemSetting.APPOINTMENT_REMINDER_OFFSET_MINUTES
        SystemSetting.objects.filter(key=reminder_key).delete()
        minimum = SystemSetting.objects.get(key=SystemSetting.BOOKING_MIN_LEAD_MINUTES)
        minimum.description = "Preserve this existing description."
        minimum.save(update_fields=["description"])
        unrelated = SystemSetting.objects.create(
            key=SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR,
            value="17",
            value_type=SystemSetting.ValueType.INTEGER,
            description="Unrelated rate limit.",
        )
        existing_appointment = self.create_scheduling_appointment(self.future_date(2))
        original_reminder_offset = existing_appointment.reminder_offset
        url = self.action_url("dashboard_scheduling_rules_update", language="en")
        self.client.force_login(self.staff)

        invalid_cases = {
            "booking_enabled": "maybe",
            "booking_min_lead_minutes": "-1",
            "booking_max_days_ahead": "0",
            "booking_slot_interval_minutes": "0",
            "appointment_reminder_offset_minutes": "-1",
        }
        for field_name, invalid_value in invalid_cases.items():
            with self.subTest(field_name=field_name):
                response = self.client.post(
                    url,
                    self.rules_payload(**{field_name: invalid_value}),
                )
                self.assertEqual(response.status_code, 400)
        for field_name, above_defensive_limit in (
            ("booking_min_lead_minutes", "5256001"),
            ("booking_max_days_ahead", "3651"),
            ("booking_slot_interval_minutes", "5256001"),
            ("appointment_reminder_offset_minutes", "5256001"),
        ):
            with self.subTest(field_name=field_name, boundary="defensive-maximum"):
                response = self.client.post(
                    url,
                    self.rules_payload(**{field_name: above_defensive_limit}),
                )
                self.assertEqual(response.status_code, 400)

        response = self.client.post(
            url,
            self.rules_payload(
                booking_enabled="false",
                booking_min_lead_minutes="45",
                booking_max_days_ahead="45",
                booking_slot_interval_minutes="20",
                appointment_reminder_offset_minutes="90",
            ),
        )
        self.assertEqual(response.status_code, 302)
        effective = booking_services.get_booking_settings()
        self.assertFalse(effective.enabled)
        self.assertEqual(effective.min_lead_minutes, 45)
        self.assertEqual(effective.max_days_ahead, 45)
        self.assertEqual(effective.slot_interval_minutes, 20)
        self.assertEqual(effective.reminder_offset_minutes, 90)

        expected_types = {
            SystemSetting.BOOKING_ENABLED: SystemSetting.ValueType.BOOLEAN,
            SystemSetting.BOOKING_MIN_LEAD_MINUTES: SystemSetting.ValueType.INTEGER,
            SystemSetting.BOOKING_MAX_DAYS_AHEAD: SystemSetting.ValueType.INTEGER,
            SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES: SystemSetting.ValueType.INTEGER,
            SystemSetting.APPOINTMENT_REMINDER_OFFSET_MINUTES: SystemSetting.ValueType.DURATION_MINUTES,
        }
        for key, value_type in expected_types.items():
            setting = SystemSetting.objects.get(key=key)
            self.assertEqual(setting.value_type, value_type)
        minimum.refresh_from_db()
        self.assertEqual(minimum.description, "Preserve this existing description.")
        unrelated.refresh_from_db()
        self.assertEqual((unrelated.value, unrelated.description), ("17", "Unrelated rate limit."))
        existing_appointment.refresh_from_db()
        self.assertEqual(existing_appointment.reminder_offset, original_reminder_offset)

        audits = AuditLog.objects.filter(action=AuditLog.Action.SETTINGS_CHANGE)
        self.assertEqual(audits.count(), 5)
        self.assertEqual(
            {audit.metadata["key"] for audit in audits},
            set(expected_types),
        )
        for audit in audits:
            self.assertEqual(set(audit.metadata), {"key", "old_value", "new_value"})

    def test_booking_rule_changes_flow_directly_into_public_availability(self):
        target_date = self.future_date(3)
        self.create_schedule(target_date, time(9, 0), time(10, 0))
        url = self.action_url("dashboard_scheduling_rules_update")
        self.client.force_login(self.staff)

        self.client.post(url, self.rules_payload(booking_enabled="false"))
        self.assertEqual(
            booking_services.generate_available_slots(
                self.short_visit,
                target_date=target_date,
                doctor=self.doctor,
            ),
            [],
        )

        self.client.post(
            url,
            self.rules_payload(booking_min_lead_minutes="5256000"),
        )
        self.assertEqual(
            booking_services.generate_available_slots(
                self.short_visit,
                target_date=target_date,
                doctor=self.doctor,
            ),
            [],
        )

        self.client.post(url, self.rules_payload(booking_max_days_ahead="1"))
        self.assertEqual(
            booking_services.generate_available_slots(
                self.short_visit,
                target_date=target_date,
                doctor=self.doctor,
            ),
            [],
        )

        updated = self.client.post(
            url,
            self.rules_payload(
                booking_slot_interval_minutes="30",
                appointment_reminder_offset_minutes="75",
            ),
        )
        self.assertEqual(updated.status_code, 302)
        slots = booking_services.generate_available_slots(
            self.short_visit,
            target_date=target_date,
            doctor=self.doctor,
        )
        self.assertEqual(len(slots), 2)
        self.assertEqual(booking_services.get_booking_settings().reminder_offset_minutes, 75)

    def test_each_allowed_booking_key_can_update_and_be_recreated_without_touching_others(self):
        cases = (
            (
                "booking_enabled",
                SystemSetting.BOOKING_ENABLED,
                "false",
                SystemSetting.ValueType.BOOLEAN,
            ),
            (
                "booking_min_lead_minutes",
                SystemSetting.BOOKING_MIN_LEAD_MINUTES,
                "25",
                SystemSetting.ValueType.INTEGER,
            ),
            (
                "booking_max_days_ahead",
                SystemSetting.BOOKING_MAX_DAYS_AHEAD,
                "25",
                SystemSetting.ValueType.INTEGER,
            ),
            (
                "booking_slot_interval_minutes",
                SystemSetting.BOOKING_SLOT_INTERVAL_MINUTES,
                "25",
                SystemSetting.ValueType.INTEGER,
            ),
            (
                "appointment_reminder_offset_minutes",
                SystemSetting.APPOINTMENT_REMINDER_OFFSET_MINUTES,
                "25",
                SystemSetting.ValueType.DURATION_MINUTES,
            ),
        )
        unrelated = SystemSetting.objects.create(
            key=SystemSetting.BOOKING_PHONE_RATE_LIMIT_PER_DAY,
            value="91",
            value_type=SystemSetting.ValueType.INTEGER,
            description="Must remain untouched.",
        )
        url = self.action_url("dashboard_scheduling_rules_update")
        self.client.force_login(self.staff)
        for field_name, key, desired_value, expected_type in cases:
            with self.subTest(field_name=field_name, operation="update"):
                setting, _ = SystemSetting.objects.update_or_create(
                    key=key,
                    defaults={
                        "value": "999" if field_name != "booking_enabled" else "true",
                        "value_type": expected_type,
                        "description": f"Preserved description for {field_name}.",
                    },
                )
                payload = self.rules_payload(**{field_name: desired_value})
                self.assertEqual(self.client.post(url, payload).status_code, 302)
                setting.refresh_from_db()
                self.assertEqual(setting.value, desired_value)
                self.assertEqual(setting.value_type, expected_type)
                self.assertEqual(
                    setting.description,
                    f"Preserved description for {field_name}.",
                )
            with self.subTest(field_name=field_name, operation="recreate"):
                SystemSetting.objects.filter(key=key).delete()
                self.assertEqual(self.client.post(url, payload).status_code, 302)
                recreated = SystemSetting.objects.get(key=key)
                self.assertEqual(recreated.value, desired_value)
                self.assertEqual(recreated.value_type, expected_type)
            unrelated.refresh_from_db()
            self.assertEqual(
                (unrelated.value, unrelated.description),
                ("91", "Must remain untouched."),
            )

    def test_all_mutation_routes_enforce_login_staff_post_and_csrf(self):
        update_period = DoctorSchedule.objects.create(
            doctor=self.doctor,
            weekday=DoctorSchedule.Weekday.MONDAY,
            start_time=time(8, 0),
            end_time=time(9, 0),
        )
        deactivate_period = DoctorSchedule.objects.create(
            doctor=self.doctor,
            weekday=DoctorSchedule.Weekday.TUESDAY,
            start_time=time(8, 0),
            end_time=time(9, 0),
        )
        closure = ClosedDay.objects.create(
            doctor=self.doctor,
            date=self.future_date(12),
            reason_en="Security route closure",
        )
        special_date = self.future_date(13)
        special_update = self.create_schedule_override(
            special_date,
            time(10),
            time(11),
        )
        special_deactivate = self.create_schedule_override(
            special_date,
            time(12),
            time(13),
        )
        special_use_weekly = self.create_schedule_override(
            special_date,
            time(14),
            time(15),
        )
        cases = [
            (
                "weekly-create",
                self.action_url("dashboard_scheduling_weekly_create", language="en"),
                {"weekday": DoctorSchedule.Weekday.WEDNESDAY, "start_time": "10:00", "end_time": "11:00"},
            ),
            (
                "weekly-update",
                self.action_url(
                    "dashboard_scheduling_weekly_update",
                    language="en",
                    period_id=update_period.pk,
                ),
                {"start_time": "08:00", "end_time": "09:30"},
            ),
            (
                "weekly-deactivate",
                self.action_url(
                    "dashboard_scheduling_weekly_deactivate",
                    language="en",
                    period_id=deactivate_period.pk,
                ),
                {},
            ),
            (
                "closure-create",
                self.action_url("dashboard_scheduling_closure_create", language="en"),
                {"date": self.future_date(11).isoformat(), "reason_ar": "", "reason_en": "Security create"},
            ),
            (
                "closure-deactivate",
                self.action_url(
                    "dashboard_scheduling_closure_deactivate",
                    language="en",
                    closure_id=closure.pk,
                ),
                {},
            ),
            (
                "special-create",
                self.action_url("dashboard_scheduling_special_create", language="en"),
                {
                    "date": self.future_date(14).isoformat(),
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "reason_ar": "",
                    "reason_en": "Security Special Hours",
                },
            ),
            (
                "special-update",
                self.action_url(
                    "dashboard_scheduling_special_update",
                    language="en",
                    period_id=special_update.pk,
                ),
                {
                    "date": special_date.isoformat(),
                    "start_time": "10:00",
                    "end_time": "11:30",
                    "reason_ar": "",
                    "reason_en": "Security update",
                },
            ),
            (
                "special-deactivate",
                self.action_url(
                    "dashboard_scheduling_special_deactivate",
                    language="en",
                    period_id=special_deactivate.pk,
                ),
                {},
            ),
            (
                "special-use-weekly",
                self.action_url(
                    "dashboard_scheduling_special_use_weekly",
                    language="en",
                ),
                {"date": special_date.isoformat()},
            ),
            (
                "service-duration",
                self.action_url(
                    "dashboard_scheduling_service_duration",
                    language="en",
                    visit_type_id=self.long_visit.pk,
                ),
                {"duration_minutes": "50"},
            ),
            (
                "booking-rules",
                self.action_url("dashboard_scheduling_rules_update", language="en"),
                self.rules_payload(),
            ),
        ]
        for label, url, payload in cases:
            with self.subTest(label=label, boundary="anonymous"):
                anonymous = Client().post(url, payload)
                self.assertEqual(anonymous.status_code, 302)
                self.assertTrue(anonymous["Location"].startswith(f"{reverse('login_en')}?role=doctor&next="))
            with self.subTest(label=label, boundary="non-staff"):
                non_staff_client = Client()
                non_staff_client.force_login(self.normal_user)
                self.assertEqual(non_staff_client.post(url, payload).status_code, 403)
            with self.subTest(label=label, boundary="GET"):
                staff_client = Client()
                staff_client.force_login(self.staff)
                self.assertEqual(staff_client.get(url).status_code, 405)
            with self.subTest(label=label, boundary="CSRF"):
                csrf_client = Client(enforce_csrf_checks=True)
                csrf_client.force_login(self.staff)
                self.assertEqual(csrf_client.post(url, payload).status_code, 403)
                token_response = csrf_client.get(self.scheduling_url(lang="en", section="weekly"))
                self.assertEqual(token_response.status_code, 200)
                csrf_token = csrf_client.cookies["csrftoken"].value
                allowed = csrf_client.post(
                    url,
                    {**payload, "csrfmiddlewaretoken": csrf_token},
                )
                self.assertEqual(allowed.status_code, 302)

    def test_management_controls_fail_safely_without_active_doctor(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=["is_active"])
        self.client.force_login(self.staff)
        response = self.scheduling(lang="en", section="weekly")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Management is currently unavailable")
        self.assertNotContains(response, "Add period")
        mutation = self.client.post(
            self.action_url("dashboard_scheduling_weekly_create", language="en"),
            {"weekday": 0, "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertEqual(mutation.status_code, 409)
        self.assertFalse(DoctorSchedule.objects.exists())
        special_mutation = self.client.post(
            self.action_url("dashboard_scheduling_special_create", language="en"),
            {
                "date": self.future_date().isoformat(),
                "start_time": "12:00",
                "end_time": "15:00",
                "reason_ar": "",
                "reason_en": "Unavailable",
            },
        )
        self.assertEqual(special_mutation.status_code, 409)
        self.assertFalse(DoctorScheduleOverride.objects.exists())

    def test_management_changes_are_visible_through_the_existing_public_booking_page(self):
        target_date = self.future_date(3)
        self.client.force_login(self.staff)

        def public_slot_count():
            response = self.client.get(
                reverse("booking_slots_en"),
                {"visit_type": self.short_visit.pk, "date": target_date.isoformat()},
            )
            self.assertEqual(response.status_code, 200)
            group = next(
                (
                    item
                    for item in response.context.get("grouped_slots", [])
                    if item["date"] == target_date
                ),
                None,
            )
            return len(group["slots"]) if group else 0

        self.client.post(
            self.action_url("dashboard_scheduling_weekly_create"),
            {
                "weekday": target_date.weekday(),
                "start_time": "09:00",
                "end_time": "10:00",
            },
        )
        self.assertEqual(public_slot_count(), 4)

        self.client.post(
            self.action_url(
                "dashboard_scheduling_service_duration",
                visit_type_id=self.short_visit.pk,
            ),
            {"duration_minutes": "60"},
        )
        self.assertEqual(public_slot_count(), 1)

        self.client.post(
            self.action_url("dashboard_scheduling_closure_create"),
            {"date": target_date.isoformat(), "reason_ar": "", "reason_en": "Public flow closure"},
        )
        self.assertEqual(public_slot_count(), 0)
        closure = ClosedDay.objects.get(doctor=self.doctor, date=target_date)
        self.client.post(
            self.action_url(
                "dashboard_scheduling_closure_deactivate",
                closure_id=closure.pk,
            )
        )
        self.assertEqual(public_slot_count(), 1)

        self.client.post(
            self.action_url("dashboard_scheduling_rules_update"),
            self.rules_payload(booking_enabled="false"),
        )
        disabled = self.client.get(
            reverse("booking_slots_en"),
            {"visit_type": self.short_visit.pk},
        )
        self.assertContains(disabled, "Online booking is currently unavailable")

        self.client.post(
            self.action_url(
                "dashboard_scheduling_service_duration",
                visit_type_id=self.short_visit.pk,
            ),
            {"duration_minutes": "15"},
        )
        self.client.post(
            self.action_url("dashboard_scheduling_rules_update"),
            self.rules_payload(booking_slot_interval_minutes="30"),
        )
        self.assertEqual(public_slot_count(), 2)

    def test_management_css_contains_responsive_and_accessibility_contract(self):
        stylesheet = (
            Path(__file__).resolve().parents[2] / "static" / "css" / "dashboard-scheduling.css"
        ).read_text(encoding="utf-8")
        for contract in (
            ".scheduling-section-tabs",
            ".scheduling-period-editor",
            ".scheduling-conflict-warning",
            ".scheduling-rules-grid",
            "@media (max-width: 63.999rem)",
            "@media (max-width: 47.999rem)",
            "@media (max-width: 35rem)",
            ":focus-visible",
            "min-width: 0",
            "overflow-wrap: anywhere",
        ):
            self.assertIn(contract, stylesheet)
