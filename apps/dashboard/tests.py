from datetime import date, datetime, time, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.dashboard import views as dashboard_views
from apps.booking.models import Appointment
from apps.clinic.models import Doctor, VisitType
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
        for unavailable_label in (
            "Medical Records",
            "Scheduling",
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
