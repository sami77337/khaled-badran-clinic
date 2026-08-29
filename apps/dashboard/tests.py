import re
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
from apps.booking.models import Appointment, AppointmentStatusHistory
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
from apps.records.models import (
    IMAGE_MAX_BYTES,
    ClinicalNote,
    PublicCase,
    RecordMedia,
    RecordMediaFolder,
    VisitRecord,
)


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
        whatsapp_phone_raw="",
        whatsapp_phone_e164="",
    ):
        return Patient.objects.create(
            user=user,
            full_name=full_name,
            phone_raw=phone_raw,
            phone_e164=phone_e164,
            whatsapp_phone_raw=whatsapp_phone_raw,
            whatsapp_phone_e164=whatsapp_phone_e164,
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
        if (
            kwargs.get("visibility") == RecordMedia.Visibility.APPROVED_PUBLIC_CASE
            and "public_case" not in kwargs
        ):
            kwargs["public_case"] = PublicCase.objects.create(
                patient=patient,
                title=kwargs.get("title", "Synthetic dashboard public case")[:180],
                consent_confirmed=True,
                is_published=True,
            )
            kwargs.setdefault(
                "public_case_role",
                (
                    RecordMedia.PublicCaseRole.VIDEO
                    if media_type == RecordMedia.MediaType.SHORT_VIDEO
                    else RecordMedia.PublicCaseRole.PRIMARY
                ),
            )
        return RecordMedia.objects.create(
            patient=patient,
            media_type=media_type,
            file=file,
            title=kwargs.pop("title", "Synthetic dashboard media title"),
            description=kwargs.pop("description", "Synthetic dashboard media description."),
            **kwargs,
        )

    def create_media_folder(self, *, patient=None, name="Synthetic Media Folder", created_by=None):
        return RecordMediaFolder.objects.create(
            patient=patient or self.create_patient(),
            name=name,
            created_by=created_by,
        )

    def assert_no_cache(self, response):
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)

    def patient_record_url(self, patient, *, language="ar", fragment=None):
        url = reverse("dashboard_patient_record_detail", kwargs={"patient_id": patient.id})
        if language == "en":
            url = f"{url}?lang=en"
        return f"{url}#{fragment}" if fragment else url


class DashboardRecordAccessTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.patient = self.create_patient()
        self.staff = self.create_staff()
        self.normal_user = self.create_user(username="synthetic-dashboard-normal-user")

    def test_anonymous_cannot_access_dashboard_patient_list(self):
        response = self.client.get(reverse("dashboard_patient_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", response["Location"])
        self.assertNotIn(b"data-patient-contact-trigger", response.content)

    def test_authenticated_non_staff_gets_403_for_dashboard_patient_list(self):
        self.client.force_login(self.normal_user)

        response = self.client.get(reverse("dashboard_patient_list"))

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"data-patient-contact-trigger", response.content)

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

    def test_anonymous_english_record_workflow_redirects_to_english_doctor_login(self):
        media = self.create_media(patient=self.patient)
        urls = [
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id}),
            reverse("dashboard_visit_create", kwargs={"patient_id": self.patient.id}),
            reverse("dashboard_note_create", kwargs={"patient_id": self.patient.id}),
            reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id}),
            reverse("dashboard_public_case_create", kwargs={"patient_id": self.patient.id}),
            reverse(
                "dashboard_media_update",
                kwargs={"patient_id": self.patient.id, "public_id": media.public_id},
            ),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(f"{url}?lang=en")

                self.assertEqual(response.status_code, 302)
                self.assertIn(f"{reverse('login_en')}?role=doctor&next=", response["Location"])

    def test_non_staff_cannot_access_record_create_or_edit_pages(self):
        media = self.create_media(patient=self.patient)
        self.client.force_login(self.normal_user)
        urls = [
            reverse("dashboard_visit_create", kwargs={"patient_id": self.patient.id}),
            reverse("dashboard_note_create", kwargs={"patient_id": self.patient.id}),
            reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id}),
            reverse("dashboard_public_case_create", kwargs={"patient_id": self.patient.id}),
            reverse(
                "dashboard_media_update",
                kwargs={"patient_id": self.patient.id, "public_id": media.public_id},
            ),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)


class DashboardPatientListTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()

    def patient_list(self, **params):
        self.client.force_login(self.staff)
        return self.client.get(reverse("dashboard_patient_list"), params)

    def patient_names(self, response):
        return [patient.full_name for patient in response.context["patients"]]

    def test_uses_approved_dashboard_shell_and_active_patients_navigation(self):
        patient = self.create_patient(full_name="Dashboard Shell Patient")

        response = self.patient_list()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard/patient_list.html")
        self.assertTemplateUsed(response, "dashboard/base.html")
        self.assertTemplateNotUsed(response, "base.html")
        self.assertEqual(response.context["active_dashboard_nav"], "patients")
        self.assertContains(response, '<body class="dashboard-shell is-rtl">')
        self.assertContains(response, 'class="dashboard-nav-link is-active"')
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, "css/dashboard-patients.css")
        self.assertContains(response, patient.full_name)
        for legacy_fragment in (
            'class="site-shell',
            'class="page-hero',
            'class="booking-steps',
            'class="trust-note',
            "لوحة داخلية للطاقم",
            "المرضى والسجلات",
            "<footer",
        ):
            self.assertNotContains(response, legacy_fragment)

    def test_defaults_to_arabic_rtl_and_supports_english_ltr_with_page_switch(self):
        self.create_patient(full_name="Bilingual Patient")

        arabic = self.patient_list()
        english = self.patient_list(lang="en")

        self.assertContains(arabic, '<html lang="ar" dir="rtl">')
        self.assertContains(arabic, "<h1>المرضى</h1>", html=True)
        self.assertContains(arabic, "إدارة ملفات المرضى والوصول إلى السجلات الطبية.")
        self.assertEqual(
            arabic.context["dashboard_language_switch_url"],
            f'{reverse("dashboard_patient_list")}?lang=en',
        )
        self.assertContains(english, '<html lang="en" dir="ltr">')
        self.assertContains(english, "<h1>Patients</h1>", html=True)
        self.assertContains(english, "Manage patient files and access medical records.")
        self.assertEqual(
            english.context["dashboard_language_switch_url"],
            reverse("dashboard_patient_list"),
        )
        self.assertContains(english, '<input type="hidden" name="lang" value="en">')
        self.assertContains(english, "Open Record")

    def test_open_record_button_keeps_an_explicit_white_text_state_contract(self):
        self.create_patient(full_name="Contrast Contract Patient")

        response = self.patient_list(lang="en")
        stylesheet = (
            Path(__file__).resolve().parents[2] / "static" / "css" / "dashboard-patients.css"
        ).read_text(encoding="utf-8")

        self.assertContains(response, 'class="patient-record-action"')
        self.assertIn("background: var(--dashboard-burgundy);", stylesheet)
        for state in ("", ":link", ":visited", ":hover", ":focus-visible", ":active"):
            self.assertIn(f".dashboard-shell .patient-record-action{state}", stylesheet)
        self.assertIn("color: #fff;", stylesheet)

    def test_contact_action_and_menu_labels_render_in_arabic_and_english(self):
        self.create_patient(full_name="Bilingual Contact Patient")

        arabic = self.patient_list()
        english = self.patient_list(lang="en")

        self.assertContains(arabic, 'class="patient-contact-trigger"')
        self.assertContains(arabic, "تواصل")
        self.assertContains(arabic, "اتصال")
        self.assertContains(arabic, "نسخ الرقم")
        self.assertContains(arabic, 'data-copy-success="تم نسخ الرقم"')
        self.assertContains(english, 'class="patient-contact-trigger"')
        self.assertContains(english, "Contact")
        self.assertContains(english, "Call")
        self.assertContains(english, "Copy number")
        self.assertContains(english, 'data-copy-success="Number copied"')

    def test_language_switch_preserves_the_trimmed_search_on_patients_page(self):
        patient = self.create_patient(full_name="Switch Search Patient")

        arabic = self.patient_list(q="  Switch Search  ")
        english_switch = urlsplit(arabic.context["dashboard_language_switch_url"])

        self.assertEqual(english_switch.path, reverse("dashboard_patient_list"))
        self.assertEqual(parse_qs(english_switch.query), {"lang": ["en"], "q": ["Switch Search"]})
        self.assertContains(arabic, patient.full_name)

        english = self.patient_list(lang="en", q="Switch Search")
        arabic_switch = urlsplit(english.context["dashboard_language_switch_url"])
        self.assertEqual(arabic_switch.path, reverse("dashboard_patient_list"))
        self.assertEqual(parse_qs(arabic_switch.query), {"q": ["Switch Search"]})

    def test_summary_and_each_patient_row_use_real_annotated_counts(self):
        patient = self.create_patient(full_name="Counted Patient")
        first_visit = self.create_visit(patient=patient)
        self.create_visit(patient=patient)
        self.create_note(patient=patient, visit=first_visit)
        self.create_note(patient=patient)
        self.create_media(patient=patient)

        response = self.patient_list(lang="en")
        rendered_patient = list(response.context["patients"])[0]

        self.assertEqual(response.context["total_patient_count"], 1)
        self.assertEqual(rendered_patient.visit_count, 2)
        self.assertEqual(rendered_patient.note_count, 2)
        self.assertEqual(rendered_patient.media_count, 1)
        self.assertContains(response, "Total patients")
        self.assertContains(response, "Visits")
        self.assertContains(response, "Notes")
        self.assertContains(response, "Media")

    def test_searches_real_patients_by_name_and_trims_whitespace(self):
        matching = self.create_patient(full_name="Amal Synthetic Search")
        hidden = self.create_patient(
            full_name="Different Patient",
            phone_raw="+962700000010",
            phone_e164="+962700000010",
        )

        response = self.patient_list(q="  synthetic search  ")

        self.assertEqual(response.context["patient_search_query"], "synthetic search")
        self.assertEqual(self.patient_names(response), [matching.full_name])
        self.assertContains(response, matching.full_name)
        self.assertNotContains(response, hidden.full_name)

    def test_searches_real_patients_by_raw_and_e164_phone(self):
        raw_match = self.create_patient(
            full_name="Raw Phone Match",
            phone_raw="0798888777",
            phone_e164="",
        )
        e164_match = self.create_patient(
            full_name="E164 Phone Match",
            phone_raw="0791234567",
            phone_e164="+962791234567",
        )
        self.create_patient(
            full_name="Unmatched Phone",
            phone_raw="0780000000",
            phone_e164="+962780000000",
        )

        raw_response = self.patient_list(q="8888")
        e164_response = self.patient_list(q="+96279123")

        self.assertEqual(self.patient_names(raw_response), [raw_match.full_name])
        self.assertEqual(self.patient_names(e164_response), [e164_match.full_name])

    def test_call_action_prefers_safe_normalized_phone(self):
        patient = self.create_patient(
            full_name="Normalized Call Patient",
            phone_raw="0791234567",
            phone_e164="+962791234567",
        )

        response = self.patient_list(lang="en")

        self.assertContains(response, f'href="tel:{patient.phone_e164}"')
        self.assertNotContains(response, f'href="tel:{patient.phone_raw}"')

    def test_call_action_uses_only_a_defensively_sanitized_raw_fallback(self):
        self.create_patient(
            full_name="Safe Raw Call Patient",
            phone_raw="(079) 123-4567",
            phone_e164="",
        )
        unsafe_phone = "0791234567;ext=9"
        self.create_patient(
            full_name="Unsafe Raw Call Patient",
            phone_raw=unsafe_phone,
            phone_e164="",
        )

        response = self.patient_list(lang="en")

        self.assertContains(response, 'href="tel:0791234567"')
        self.assertNotContains(response, f'href="tel:{unsafe_phone}"')

    def test_whatsapp_action_uses_dedicated_valid_e164_digits_only(self):
        whatsapp_phone = "+962799876543"
        patient = self.create_patient(
            full_name="Dedicated WhatsApp Patient",
            phone_raw="0791111111",
            phone_e164="+962791111111",
            whatsapp_phone_raw="0799876543",
            whatsapp_phone_e164=whatsapp_phone,
        )

        response = self.patient_list(lang="en")
        page = response.content.decode()
        targets = re.findall(r'href="(https://wa\.me/[^"]+)"', page)

        self.assertEqual(targets, [f"https://wa.me/{whatsapp_phone[1:]}"])
        target = urlsplit(targets[0])
        self.assertEqual(target.scheme, "https")
        self.assertEqual(target.netloc, "wa.me")
        self.assertTrue(target.path.removeprefix("/").isdigit())
        self.assertNotIn("+", target.path)
        self.assertContains(response, "WhatsApp")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertNotContains(response, patient.whatsapp_phone_raw)

    def test_whatsapp_does_not_fall_back_to_primary_or_raw_whatsapp_phone(self):
        patient = self.create_patient(
            full_name="No Dedicated Target Patient",
            phone_raw="0792222222",
            phone_e164="+962792222222",
            whatsapp_phone_raw="0793333333",
            whatsapp_phone_e164="",
        )

        response = self.patient_list(lang="en")

        self.assertNotContains(response, "WhatsApp")
        self.assertNotContains(response, "https://wa.me/")
        self.assertNotContains(response, patient.whatsapp_phone_raw)

    def test_invalid_whatsapp_e164_does_not_render_an_action(self):
        self.create_patient(
            full_name="Invalid Dedicated Target Patient",
            whatsapp_phone_raw="0794444444",
            whatsapp_phone_e164="+962 79 444 4444",
        )

        response = self.patient_list(lang="en")

        self.assertNotContains(response, "WhatsApp")
        self.assertNotContains(response, "https://wa.me/")

    def test_search_query_is_defensively_bounded(self):
        response = self.patient_list(q=f"  {'x' * 150}  ")

        self.assertEqual(
            response.context["patient_search_query"],
            "x" * dashboard_views.PATIENT_SEARCH_MAX_LENGTH,
        )
        self.assertContains(
            response,
            f'maxlength="{dashboard_views.PATIENT_SEARCH_MAX_LENGTH}"',
        )

    def test_empty_database_state_is_bilingual_and_not_a_table_row(self):
        arabic = self.patient_list()
        english = self.patient_list(lang="en")

        self.assertContains(arabic, "لا توجد ملفات مرضى بعد.")
        self.assertContains(english, "No patient files yet.")
        self.assertNotContains(arabic, "<table")
        self.assertNotContains(english, "<table")

    def test_no_matching_search_state_is_distinct_and_easy_to_clear(self):
        self.create_patient(full_name="Existing Patient")

        arabic = self.patient_list(q="No Such Patient")
        english = self.patient_list(lang="en", q="No Such Patient")

        self.assertContains(arabic, "لا توجد نتائج مطابقة.")
        self.assertNotContains(arabic, "لا توجد ملفات مرضى بعد.")
        self.assertContains(english, "No matching patients found.")
        self.assertNotContains(english, "No patient files yet.")
        self.assertContains(english, "Clear search", count=2)
        self.assertEqual(
            english.context["patient_search_clear_url"],
            f'{reverse("dashboard_patient_list")}?lang=en',
        )

    def test_long_name_wraps_and_phone_has_ltr_direction_contract(self):
        long_name = (
            "Long English Patient Name With Multiple Components That Must Wrap Safely "
            "Without Expanding The Dashboard Viewport"
        )
        phone = "+962791234567"
        self.create_patient(full_name=long_name, phone_raw=phone, phone_e164=phone)

        response = self.patient_list(lang="en")

        self.assertContains(response, long_name)
        self.assertContains(
            response,
            f'<span class="patient-phone-number" dir="ltr">{phone}</span>',
            html=True,
        )
        stylesheet = (
            Path(__file__).resolve().parents[2] / "static" / "css" / "dashboard-patients.css"
        ).read_text(encoding="utf-8")
        self.assertIn("overflow-wrap: anywhere;", stylesheet)
        self.assertIn("@media (max-width: 35rem)", stylesheet)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", stylesheet)

    def test_contact_markup_has_unique_accessible_controls_and_mobile_bounds(self):
        self.create_patient(full_name="Accessible Contact Patient A")
        self.create_patient(
            full_name="Accessible Contact Patient B",
            phone_raw="0795550001",
            phone_e164="+962795550001",
        )

        response = self.patient_list(lang="en")
        page = response.content.decode()
        trigger_matches = re.findall(
            r'<button\s+class="patient-contact-trigger"\s+'
            r'id="([^"]+)"\s+type="button"\s+aria-expanded="false"\s+'
            r'aria-controls="([^"]+)"\s+data-patient-contact-trigger',
            page,
        )
        stylesheet = (
            Path(__file__).resolve().parents[2] / "static" / "css" / "dashboard-patients.css"
        ).read_text(encoding="utf-8")

        self.assertEqual(len(trigger_matches), 2)
        trigger_ids = [match[0] for match in trigger_matches]
        menu_ids = [match[1] for match in trigger_matches]
        self.assertEqual(len(set(trigger_ids)), 2)
        self.assertEqual(len(set(menu_ids)), 2)
        for trigger_id, menu_id in trigger_matches:
            self.assertTrue(trigger_id.startswith("patient-contact-row-"))
            self.assertEqual(menu_id, trigger_id.removesuffix("-trigger") + "-menu")
            self.assertIn(f'id="{menu_id}"', page)
            self.assertIn(f'aria-labelledby="{trigger_id}"', page)
        self.assertContains(response, 'role="group"', count=2)
        self.assertContains(response, "js/dashboard-patients.js")
        self.assertIn("width: min(13rem, calc(100vw - 2rem));", stylesheet)
        self.assertIn("max-width: calc(100vw - 2rem);", stylesheet)
        self.assertIn("max-height: calc(100vh - 2rem);", stylesheet)
        self.assertIn(".patient-contact-menu.opens-upward", stylesheet)
        self.assertIn("@media (max-width: 35rem)", stylesheet)
        self.assertIn(".patient-actions", stylesheet)

    def test_list_omits_email_and_private_clinical_or_media_fields(self):
        patient_user = self.create_user(username="patient-list-private-user")
        patient_user.email = "PATIENT-LIST-PRIVATE-EMAIL@example.test"
        patient_user.save(update_fields=["email"])
        patient = self.create_patient(
            user=patient_user,
            full_name="Privacy Reviewed Patient",
            phone_raw="0795554433",
            phone_e164="+962795554433",
        )
        patient.notes = "PATIENT-LIST-PRIVATE-PATIENT-NOTES"
        patient.whatsapp_phone_raw = "PATIENT-LIST-PRIVATE-WHATSAPP-RAW"
        patient.save(update_fields=["notes", "whatsapp_phone_raw"])
        appointment = self.create_appointment(patient)
        appointment.booking_note = "PATIENT-LIST-PRIVATE-BOOKING-NOTE"
        appointment.save(update_fields=["booking_note"])
        visit = self.create_visit(
            patient=patient,
            appointment=appointment,
            visit_reason="PATIENT-LIST-PRIVATE-VISIT-REASON",
            doctor_notes="PATIENT-LIST-PRIVATE-DOCTOR-NOTES",
            diagnosis_plan="PATIENT-LIST-PRIVATE-DIAGNOSIS",
            instructions="PATIENT-LIST-PRIVATE-INSTRUCTIONS",
            follow_up_notes="PATIENT-LIST-PRIVATE-FOLLOW-UP",
        )
        note = self.create_note(
            patient=patient,
            visit=visit,
            title="PATIENT-LIST-PRIVATE-NOTE-TITLE",
            body="PATIENT-LIST-PRIVATE-NOTE-BODY",
        )
        media = self.create_media(
            patient=patient,
            title="PATIENT-LIST-PRIVATE-MEDIA-TITLE",
            description="PATIENT-LIST-PRIVATE-MEDIA-DESCRIPTION",
        )

        response = self.patient_list(lang="en")

        self.assertContains(response, patient.full_name)
        self.assertContains(response, patient.phone)
        for private_value in (
            patient_user.email,
            patient.phone_raw,
            patient.whatsapp_phone_raw,
            patient.notes,
            appointment.booking_note,
            str(appointment.public_token),
            visit.visit_reason,
            visit.doctor_notes,
            visit.diagnosis_plan,
            visit.instructions,
            visit.follow_up_notes,
            note.title,
            note.body,
            media.title,
            media.description,
            str(media.public_id),
        ):
            self.assertNotContains(response, private_value)
        self.assertNotContains(response, "Patient ID")
        self.assertNotContains(response, "data-patient-id")

    def test_annotated_patient_rows_do_not_add_per_patient_queries(self):
        baseline_patient = self.create_patient(full_name="Query Baseline Patient")
        self.create_visit(patient=baseline_patient)
        request = RequestFactory().get(reverse("dashboard_patient_list"))
        request.user = self.staff

        with CaptureQueriesContext(connection) as baseline_capture:
            baseline_response = dashboard_views.dashboard_patient_list(request)
        self.assertEqual(baseline_response.status_code, 200)

        for index in range(6):
            patient = self.create_patient(
                full_name=f"Query Scale Patient {index}",
                phone_raw=f"+96279000{index:04d}",
                phone_e164=f"+96279000{index:04d}",
            )
            visit = self.create_visit(patient=patient)
            self.create_note(patient=patient, visit=visit)
            self.create_media(patient=patient)

        expanded_request = RequestFactory().get(reverse("dashboard_patient_list"))
        expanded_request.user = self.staff
        with CaptureQueriesContext(connection) as expanded_capture:
            expanded_response = dashboard_views.dashboard_patient_list(expanded_request)
        self.assertEqual(expanded_response.status_code, 200)

        self.assertEqual(len(expanded_capture), len(baseline_capture))


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

    def test_create_forms_use_dashboard_shell_and_localized_labels(self):
        cases = (
            (
                "dashboard_visit_create",
                ("إضافة زيارة", "تاريخ الزيارة", "التشخيص / الخطة", "حفظ الزيارة"),
                ("Add Visit", "Visit date", "Diagnosis / plan", "Save Visit"),
            ),
            (
                "dashboard_note_create",
                ("إضافة ملاحظة سريرية", "نوع الملاحظة", "نص الملاحظة", "حفظ الملاحظة"),
                ("Add Clinical Note", "Note type", "Note body", "Save Note"),
            ),
            (
                "dashboard_media_create",
                ("رفع ملف خاص", "نوع الملف", "حالة الظهور", "موافقة مؤكدة"),
                ("Upload Private Media", "Media type", "Visibility", "Confirmed consent"),
            ),
        )

        for route_name, arabic_labels, english_labels in cases:
            route = reverse(route_name, kwargs={"patient_id": self.patient.id})
            for language, labels, direction in (
                ("ar", arabic_labels, "rtl"),
                ("en", english_labels, "ltr"),
            ):
                with self.subTest(route=route_name, language=language):
                    response = self.client.get(
                        route,
                        {"lang": "en"} if language == "en" else {},
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertTemplateUsed(response, "dashboard/base.html")
                    self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
                    self.assertContains(response, 'class="dashboard-sidebar"')
                    self.assertContains(response, "css/dashboard-patient-record.css")
                    self.assertEqual(response.context["active_dashboard_nav"], "patients")
                    for label in labels:
                        self.assertContains(response, label)
                    for legacy_fragment in (
                        'class="site-shell',
                        'class="page-hero',
                        'class="booking-form',
                        'class="booking-steps',
                        'class="trust-note',
                    ):
                        self.assertNotContains(response, legacy_fragment)

    def test_media_create_form_limits_generic_upload_to_private_visibility_states(self):
        response = self.client.get(
            reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id}),
            {"lang": "en"},
        )

        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'value="private_only"')
        self.assertContains(response, 'value="visible_to_patient"')
        self.assertContains(response, "Private only")
        self.assertContains(response, "Visible to patient")
        self.assertNotContains(response, 'value="approved_public_case"')
        self.assertNotContains(response, "Approved public case")

    def test_english_form_language_switch_and_cancel_keep_patient_context(self):
        cases = (
            ("dashboard_visit_create", "visits"),
            ("dashboard_note_create", "clinical-notes"),
            ("dashboard_media_create", "private-media"),
        )
        for route_name, fragment in cases:
            with self.subTest(route_name=route_name):
                route = reverse(route_name, kwargs={"patient_id": self.patient.id})
                response = self.client.get(route, {"lang": "en"})

                self.assertEqual(response.context["dashboard_language_switch_url"], route)
                self.assertEqual(
                    response.context["cancel_url"],
                    self.patient_record_url(
                        self.patient,
                        language="en",
                        fragment=fragment,
                    ),
                )
                self.assertContains(response, self.patient.full_name)

    def test_english_successful_posts_return_to_localized_record_sections(self):
        visit_url = reverse("dashboard_visit_create", kwargs={"patient_id": self.patient.id})
        visit_response = self.client.post(
            f"{visit_url}?lang=en",
            {
                "appointment": "",
                "visit_date": "2026-01-15T10:30",
                "visit_reason": "SYNTHETIC-ENGLISH-VISIT",
            },
        )
        visit = VisitRecord.objects.get(patient=self.patient)
        note_url = reverse("dashboard_note_create", kwargs={"patient_id": self.patient.id})
        note_response = self.client.post(
            f"{note_url}?lang=en",
            {
                "visit": str(visit.id),
                "note_type": ClinicalNote.NoteType.DOCTOR_NOTE,
                "title": "SYNTHETIC-ENGLISH-NOTE",
                "body": "SYNTHETIC-ENGLISH-NOTE-BODY",
            },
        )
        media_url = reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id})
        media_response = self.client.post(
            f"{media_url}?lang=en",
            {
                "visit": str(visit.id),
                "media_type": RecordMedia.MediaType.IMAGE,
                "file": self.synthetic_image_file(name="synthetic-english-image.jpg"),
                "title": "SYNTHETIC-ENGLISH-MEDIA",
                "description": "SYNTHETIC-ENGLISH-MEDIA-DESCRIPTION",
                "visibility": RecordMedia.Visibility.PRIVATE_ONLY,
                "is_active": "on",
            },
        )

        self.assertRedirects(
            visit_response,
            self.patient_record_url(self.patient, language="en", fragment="visits"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            note_response,
            self.patient_record_url(
                self.patient,
                language="en",
                fragment="clinical-notes",
            ),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            media_response,
            self.patient_record_url(
                self.patient,
                language="en",
                fragment="private-media",
            ),
            fetch_redirect_response=False,
        )

    def test_generic_media_rejects_public_visibility_in_both_languages(self):
        route = reverse("dashboard_media_create", kwargs={"patient_id": self.patient.id})
        payload = {
            "visit": "",
            "media_type": RecordMedia.MediaType.IMAGE,
            "file": self.synthetic_image_file(name="synthetic-consent-ar.jpg"),
            "title": "SYNTHETIC-CONSENT-AR",
            "visibility": RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            "is_active": "on",
        }
        arabic = self.client.post(route, payload)
        english_payload = {
            **payload,
            "file": self.synthetic_image_file(name="synthetic-consent-en.jpg"),
            "title": "SYNTHETIC-CONSENT-EN",
        }
        english = self.client.post(f"{route}?lang=en", english_payload)

        self.assertContains(
            arabic,
            "حدد خيارا صحيحا.",
            status_code=400,
        )
        self.assertContains(
            english,
            "Select a valid choice.",
            status_code=400,
        )
        self.assertEqual(RecordMedia.objects.filter(patient=self.patient).count(), 0)

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
            self.patient_record_url(self.patient, fragment="visits"),
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
            self.patient_record_url(self.patient, fragment="clinical-notes"),
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
            self.patient_record_url(self.patient, fragment="private-media"),
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
            self.patient_record_url(self.patient, fragment="private-media"),
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
        self.assertContains(response, "امتداد ملف الصورة غير مدعوم.", status_code=400)
        self.assertEqual(RecordMedia.objects.filter(patient=self.patient).count(), 0)

    def test_generic_media_cannot_create_approved_public_case_orphan(self):
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
        self.assertContains(response, "حدد خيارا صحيحا.", status_code=400)
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


class DashboardMediaFolderWorkflowTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.normal_user = self.create_user(username="synthetic-folder-normal-user")
        self.patient = self.create_patient()
        self.other_patient = self.create_patient(
            full_name="Synthetic Folder Other Patient",
            phone_raw="+962700000077",
            phone_e164="+962700000077",
        )
        self.client.force_login(self.staff)

    def folder_create_url(self, patient=None):
        return reverse(
            "dashboard_media_folder_create",
            kwargs={"patient_id": (patient or self.patient).pk},
        )

    def folder_route(self, route_name, folder, patient=None):
        return reverse(
            route_name,
            kwargs={
                "patient_id": (patient or self.patient).pk,
                "folder_id": folder.pk,
            },
        )

    def test_folder_mutations_require_staff_post_and_csrf(self):
        anonymous = Client().post(self.folder_create_url(), {"name": "Blocked"})
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", anonymous["Location"])

        normal_client = Client()
        normal_client.force_login(self.normal_user)
        self.assertEqual(
            normal_client.post(self.folder_create_url(), {"name": "Blocked"}).status_code,
            403,
        )
        self.assertEqual(self.client.get(self.folder_create_url()).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(
            csrf_client.post(self.folder_create_url(), {"name": "Blocked"}).status_code,
            403,
        )
        self.assertFalse(RecordMediaFolder.objects.exists())

    def test_create_duplicate_rename_and_bilingual_folder_ui(self):
        created = self.client.post(
            f"{self.folder_create_url()}?lang=en",
            {"name": "  Procedure Photos  "},
        )
        folder = RecordMediaFolder.objects.get(patient=self.patient)
        self.assertEqual(folder.name, "Procedure Photos")
        self.assertRedirects(
            created,
            self.patient_record_url(self.patient, language="en").replace(
                "#private-media",
                "",
            )
            + f"&folder={folder.pk}#private-media",
            fetch_redirect_response=False,
        )

        duplicate = self.client.post(
            f"{self.folder_create_url()}?lang=en",
            {"name": "procedure photos"},
        )
        self.assertContains(
            duplicate,
            "A folder with this name already exists for this patient.",
            status_code=400,
        )
        self.assertEqual(RecordMediaFolder.objects.filter(patient=self.patient).count(), 1)

        renamed = self.client.post(
            f"{self.folder_route('dashboard_media_folder_rename', folder)}?lang=en",
            {"name": "Follow Up"},
        )
        self.assertEqual(renamed.status_code, 302)
        folder.refresh_from_db()
        self.assertEqual(folder.name, "Follow Up")

        arabic_ui = self.client.get(self.patient_record_url(self.patient))
        english_ui = self.client.get(self.patient_record_url(self.patient, language="en"))
        for label in ("مجلد جديد", "اسم المجلد", "إنشاء المجلد", "بدون مجلد"):
            self.assertContains(arabic_ui, label)
        for label in ("New Folder", "Folder name", "Create Folder", "Unfiled"):
            self.assertContains(english_ui, label)
        self.assertContains(english_ui, "Follow Up")
        self.assertContains(english_ui, "?lang=en")

        audit_events = set(AuditLog.objects.values_list("metadata__action", flat=True))
        self.assertIn("media_folder_created", audit_events)
        self.assertIn("media_folder_renamed", audit_events)
        self.assertNotIn(self.patient.full_name, str(list(AuditLog.objects.values())))

    def test_folder_filtering_and_delete_are_non_destructive(self):
        folder = self.create_media_folder(patient=self.patient, name="Filtered Folder")
        filed = self.create_media(patient=self.patient, folder=folder, title="Filed media item")
        unfiled = self.create_media(patient=self.patient, title="Unfiled media item")
        stored_name = filed.file.name

        all_response = self.client.get(self.patient_record_url(self.patient, language="en"))
        folder_response = self.client.get(
            self.patient_record_url(self.patient, language="en"),
            {"folder": str(folder.pk), "lang": "en"},
        )
        unfiled_response = self.client.get(
            self.patient_record_url(self.patient, language="en"),
            {"folder": "unfiled", "lang": "en"},
        )
        self.assertContains(all_response, "Filed media item")
        self.assertContains(all_response, "Unfiled media item")
        self.assertContains(folder_response, "Filed media item")
        self.assertNotContains(folder_response, "Unfiled media item")
        self.assertContains(unfiled_response, "Unfiled media item")
        self.assertNotContains(unfiled_response, "Filed media item")
        self.assertIn(f"folder={folder.pk}", folder_response.context["dashboard_language_switch_url"])

        delete_url = self.folder_route("dashboard_media_folder_delete", folder)
        confirmation = self.client.get(f"{delete_url}?lang=en")
        self.assertContains(
            confirmation,
            "Deleting this folder will not delete media. Its files will become Unfiled.",
        )
        self.assertTrue(RecordMediaFolder.objects.filter(pk=folder.pk).exists())

        deleted = self.client.post(f"{delete_url}?lang=en")
        self.assertEqual(deleted.status_code, 302)
        filed.refresh_from_db()
        unfiled.refresh_from_db()
        self.assertIsNone(filed.folder_id)
        self.assertEqual(filed.file.name, stored_name)
        self.assertEqual(RecordMedia.objects.filter(pk__in=[filed.pk, unfiled.pk]).count(), 2)

    def test_patient_folder_ownership_is_enforced_for_routes_upload_and_edit(self):
        own_folder = self.create_media_folder(patient=self.patient, name="Own Folder")
        other_folder = self.create_media_folder(patient=self.other_patient, name="Other Folder")
        media = self.create_media(
            patient=self.patient,
            folder=own_folder,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
        )

        for route_name in (
            "dashboard_media_folder_rename",
            "dashboard_media_folder_delete",
        ):
            with self.subTest(route=route_name):
                response = self.client.post(
                    self.folder_route(route_name, other_folder),
                    {"name": "Blocked Rename"},
                )
                self.assertEqual(response.status_code, 404)

        upload_url = reverse("dashboard_media_create", kwargs={"patient_id": self.patient.pk})
        rejected_upload = self.client.post(
            f"{upload_url}?lang=en",
            {
                "folder": str(other_folder.pk),
                "media_type": RecordMedia.MediaType.IMAGE,
                "file": self.synthetic_image_file(name="cross-folder-upload.jpg"),
                "visibility": RecordMedia.Visibility.PRIVATE_ONLY,
                "is_active": "on",
            },
        )
        self.assertContains(rejected_upload, "Select a valid choice.", status_code=400)

        accepted_upload = self.client.post(
            f"{upload_url}?lang=en",
            {
                "folder": str(own_folder.pk),
                "media_type": RecordMedia.MediaType.IMAGE,
                "file": self.synthetic_image_file(name="own-folder-upload.jpg"),
                "visibility": RecordMedia.Visibility.PRIVATE_ONLY,
                "is_active": "on",
            },
        )
        self.assertEqual(accepted_upload.status_code, 302)
        self.assertTrue(
            RecordMedia.objects.filter(
                patient=self.patient,
                folder=own_folder,
                original_filename="own-folder-upload.jpg",
            ).exists()
        )

        edit_url = reverse(
            "dashboard_media_update",
            kwargs={"patient_id": self.patient.pk, "public_id": media.public_id},
        )
        rejected_move = self.client.post(
            f"{edit_url}?lang=en",
            {
                "folder": str(other_folder.pk),
                "title": media.title,
                "description": media.description,
                "visibility": media.visibility,
                "is_active": "on",
            },
        )
        self.assertContains(rejected_move, "Select a valid choice.", status_code=400)
        media.refresh_from_db()
        self.assertEqual(media.folder, own_folder)

    def test_media_move_preserves_file_and_visibility_and_logs_safe_ids(self):
        first = self.create_media_folder(patient=self.patient, name="First Folder")
        second = self.create_media_folder(patient=self.patient, name="Second Folder")
        media = self.create_media(
            patient=self.patient,
            folder=first,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
        )
        stored_name = media.file.name
        edit_url = reverse(
            "dashboard_media_update",
            kwargs={"patient_id": self.patient.pk, "public_id": media.public_id},
        )

        response = self.client.post(
            f"{edit_url}?lang=en",
            {
                "folder": str(second.pk),
                "title": media.title,
                "description": media.description,
                "visibility": media.visibility,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        media.refresh_from_db()
        self.assertEqual(media.folder, second)
        self.assertEqual(media.file.name, stored_name)
        self.assertEqual(media.visibility, RecordMedia.Visibility.VISIBLE_TO_PATIENT)
        audit = AuditLog.objects.get(metadata__action="record_media_folder_moved")
        self.assertEqual(audit.metadata["media_public_id"], str(media.public_id))
        self.assertEqual(audit.metadata["folder_id"], second.pk)
        self.assertNotIn(first.name, str(audit.metadata))
        self.assertNotIn(second.name, str(audit.metadata))


class DashboardPublicCasePublishTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.patient = self.create_patient()
        self.visit = self.create_visit(patient=self.patient)
        self.url = reverse(
            "dashboard_public_case_create",
            kwargs={"patient_id": self.patient.id},
        )
        self.client.force_login(self.staff)

    def publish_payload(
        self,
        *,
        visit=None,
        before=None,
        after=None,
        video=None,
        before_files=None,
        after_files=None,
        video_files=None,
        video_cover=None,
        folder=None,
        title="Synthetic public-safe case title",
        note="",
        consent=True,
    ):
        payload = {
            "reference_visit": str((visit or self.visit).id),
            "case_title": title,
            "short_note": note,
        }
        if folder is not None:
            payload["folder"] = str(folder.pk)
        if before is not None:
            before_files = [before]
        if after is not None:
            after_files = [after]
        if video is not None:
            video_files = [video]
        if before_files is not None:
            payload["before_images"] = before_files
        if after_files is not None:
            payload["after_images"] = after_files
        if video_files is not None:
            payload["videos"] = video_files
        if video_cover is not None:
            payload["video_cover"] = video_cover
        if consent:
            payload["consent_confirmed"] = "on"
        return payload

    def test_patient_record_action_is_secondary_and_preserves_language(self):
        arabic = self.client.get(
            reverse(
                "dashboard_patient_record_detail",
                kwargs={"patient_id": self.patient.id},
            )
        )
        english = self.client.get(
            reverse(
                "dashboard_patient_record_detail",
                kwargs={"patient_id": self.patient.id},
            ),
            {"lang": "en"},
        )

        self.assertContains(
            arabic,
            f'<a class="record-action record-action-secondary" href="{self.url}">',
        )
        self.assertContains(arabic, "نشر حالة عامة")
        self.assertContains(
            english,
            f'<a class="record-action record-action-secondary" href="{self.url}?lang=en">',
        )
        self.assertContains(english, "Publish Public Case")

    def test_access_requires_login_and_staff_and_post_requires_csrf(self):
        anonymous = Client().get(self.url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", anonymous["Location"])

        normal_user = self.create_user(username="synthetic-public-case-normal-user")
        normal_client = Client()
        normal_client.force_login(normal_user)
        self.assertEqual(normal_client.get(self.url).status_code, 403)

        allowed = self.client.get(self.url)
        self.assertEqual(allowed.status_code, 200)
        self.assertTemplateUsed(allowed, "dashboard/public_case_form.html")
        self.assertTemplateUsed(allowed, "dashboard/base.html")
        self.assertEqual(allowed.context["active_dashboard_nav"], "patients")

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        csrf_response = csrf_client.post(
            self.url,
            self.publish_payload(before=self.synthetic_image_file()),
        )
        self.assertEqual(csrf_response.status_code, 403)
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

    def test_form_is_bilingual_focused_and_hides_internal_media_fields(self):
        cases = (
            (
                self.client.get(self.url),
                "ar",
                "rtl",
                (
                    "الزيارة المرجعية (اختياري)",
                    "للتنظيم الداخلي فقط، ولا تحدد كيفية تجميع الحالة في الموقع.",
                    "المجلد (اختياري)",
                    "عنوان الحالة",
                    "صور قبل",
                    "صور بعد",
                    "فيديوهات",
                    "غلاف الفيديو (اختياري)",
                    "ملاحظة عامة قصيرة (اختياري)",
                    "أؤكد أن موافقة المريض على النشر تم الحصول عليها في العيادة.",
                    "نشر الحالة",
                    "إلغاء",
                ),
            ),
            (
                self.client.get(f"{self.url}?lang=en"),
                "en",
                "ltr",
                (
                    "Reference visit (optional)",
                    "For internal record context only. It does not determine public case grouping.",
                    "Folder (optional)",
                    "Case title",
                    "Before images",
                    "After images",
                    "Videos",
                    "Video cover image (optional)",
                    "Short public note (optional)",
                    (
                        "I confirm that the patient&#x27;s consent for public display was "
                        "obtained in the clinic."
                    ),
                    "Publish Case",
                    "Cancel",
                ),
            ),
        )

        for response, language, direction, labels in cases:
            with self.subTest(language=language):
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
                self.assertContains(response, 'enctype="multipart/form-data"')
                self.assertContains(response, 'name="short_note"')
                self.assertContains(response, 'maxlength="500"')
                self.assertContains(response, 'name="case_title"')
                self.assertContains(response, 'maxlength="180"')
                self.assertContains(response, 'name="before_images"')
                self.assertContains(response, 'name="after_images"')
                self.assertContains(response, 'name="videos"')
                self.assertContains(response, 'name="video_cover"')
                self.assertContains(response, "multiple", count=3)
                self.assertNotContains(response, 'name="media_type"')
                self.assertNotContains(response, 'name="visibility"')
                for label in labels:
                    self.assertContains(response, label)

        english = cases[1][0]
        self.assertEqual(english.context["dashboard_language_switch_url"], self.url)
        self.assertEqual(
            english.context["cancel_url"],
            self.patient_record_url(
                self.patient,
                language="en",
                fragment="public-cases",
            ),
        )

    def test_patient_without_visit_can_publish_without_fake_visit(self):
        patient_without_visit = self.create_patient(
            full_name="Synthetic Patient Without Visit",
            phone_raw="+962700000099",
            phone_e164="+962700000099",
        )
        url = reverse(
            "dashboard_public_case_create",
            kwargs={"patient_id": patient_without_visit.id},
        )

        response = self.client.get(f"{url}?lang=en")
        published = self.client.post(
            f"{url}?lang=en",
            {
                "reference_visit": "",
                "case_title": "Synthetic no-visit public case",
                "before_images": [self.synthetic_image_file()],
                "consent_confirmed": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="reference_visit"')
        self.assertContains(response, 'name="before_images"')
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertEqual(published.status_code, 302)
        public_case = PublicCase.objects.get(patient=patient_without_visit)
        self.assertIsNone(public_case.reference_visit_id)
        self.assertIsNone(RecordMedia.objects.get(patient=patient_without_visit).visit_id)

    def test_reference_visit_is_optional_but_patient_scoped_and_other_fields_remain_required(self):
        other_patient = self.create_patient(
            full_name="Synthetic Other Public Case Patient",
            phone_raw="+962700000088",
            phone_e164="+962700000088",
        )
        other_visit = self.create_visit(patient=other_patient)

        no_reference_visit = self.client.post(
            f"{self.url}?lang=en",
            {
                "reference_visit": "",
                "case_title": "Synthetic missing visit case",
                "before_images": [self.synthetic_image_file(name="missing-visit.jpg")],
                "consent_confirmed": "on",
            },
        )
        cross_patient = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                visit=other_visit,
                before=self.synthetic_image_file(name="cross-patient.jpg"),
            ),
        )
        missing_media = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(),
        )
        missing_consent = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="missing-consent.jpg"),
                consent=False,
            ),
        )
        arabic_missing_consent = self.client.post(
            self.url,
            self.publish_payload(
                before=self.synthetic_image_file(name="missing-consent-ar.jpg"),
                consent=False,
            ),
        )

        self.assertEqual(no_reference_visit.status_code, 302)
        no_reference_case = PublicCase.objects.get(patient=self.patient)
        self.assertIsNone(no_reference_case.reference_visit_id)
        RecordMedia.objects.filter(public_case=no_reference_case).delete()
        no_reference_case.delete()
        self.assertContains(cross_patient, "Select a valid choice.", status_code=400)
        self.assertContains(
            missing_media,
            "Add at least one before image, after image, or video.",
            status_code=400,
        )
        self.assertContains(missing_consent, "This field is required.", status_code=400)
        self.assertContains(arabic_missing_consent, "هذا الحقل مطلوب.", status_code=400)
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())
        self.assertFalse(RecordMedia.objects.filter(patient=other_patient).exists())
        self.assertNotIn(
            other_visit,
            cross_patient.context["form"].fields["reference_visit"].queryset,
        )

    def test_all_supported_media_combinations_create_one_visit_group(self):
        combinations = (
            ("before", ("before",)),
            ("after", ("after",)),
            ("video", ("video",)),
            ("before-after", ("before", "after")),
            ("before-video", ("before", "video")),
            ("after-video", ("after", "video")),
            ("before-after-video", ("before", "after", "video")),
        )

        for label, supplied in combinations:
            with self.subTest(combination=label):
                payload = self.publish_payload(
                    before=(
                        self.synthetic_image_file(name=f"{label}-before.jpg")
                        if "before" in supplied
                        else None
                    ),
                    after=(
                        self.synthetic_image_file(name=f"{label}-after.png", content_type="image/png")
                        if "after" in supplied
                        else None
                    ),
                    video=(
                        self.synthetic_video_file(name=f"{label}-video.mp4")
                        if "video" in supplied
                        else None
                    ),
                )
                response = self.client.post(self.url, payload)

                self.assertRedirects(
                    response,
                    self.patient_record_url(self.patient, fragment="public-cases"),
                    fetch_redirect_response=False,
                )
                rows = list(RecordMedia.objects.filter(patient=self.patient).order_by("id"))
                self.assertEqual(len(rows), len(supplied))
                self.assertEqual({row.visit_id for row in rows}, {self.visit.id})
                self.assertEqual(
                    {row.visibility for row in rows},
                    {RecordMedia.Visibility.APPROVED_PUBLIC_CASE},
                )
                self.assertTrue(all(row.consent_confirmed for row in rows))
                self.assertTrue(all(row.is_active for row in rows))
                self.assertTrue(all(row.uploaded_by_id == self.staff.id for row in rows))
                public_case = PublicCase.objects.get(patient=self.patient)
                self.assertEqual({row.public_case_id for row in rows}, {public_case.pk})
                self.assertEqual(public_case.reference_visit_id, self.visit.pk)
                self.assertEqual(public_case.title, "Synthetic public-safe case title")
                self.assertTrue(public_case.consent_confirmed and public_case.is_published)
                self.assertTrue(all(row.title == "" and row.description == "" for row in rows))
                self.assertEqual(
                    sum(row.media_type == RecordMedia.MediaType.SHORT_VIDEO for row in rows),
                    int("video" in supplied),
                )
                if "before" in supplied:
                    self.assertTrue(
                        any(row.public_case_role == RecordMedia.PublicCaseRole.BEFORE for row in rows)
                    )
                if "after" in supplied:
                    self.assertTrue(
                        any(row.public_case_role == RecordMedia.PublicCaseRole.AFTER for row in rows)
                    )
                if "video" in supplied:
                    self.assertTrue(
                        any(
                            row.media_type == RecordMedia.MediaType.SHORT_VIDEO
                            and row.public_case_role == RecordMedia.PublicCaseRole.VIDEO
                            for row in rows
                        )
                    )
                RecordMedia.objects.filter(patient=self.patient).delete()
                PublicCase.objects.filter(patient=self.patient).delete()

    def test_short_note_is_optional_limited_and_stored_once_on_public_case(self):
        note = "Synthetic short public-facing case note."
        response = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="note-before.jpg"),
                after=self.synthetic_image_file(name="note-after.jpg"),
                video=self.synthetic_video_file(name="note-video.mp4"),
                note=note,
            ),
        )

        self.assertRedirects(
            response,
            self.patient_record_url(
                self.patient,
                language="en",
                fragment="public-cases",
            ),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            PublicCase.objects.get(patient=self.patient).note,
            note,
        )
        self.assertEqual(
            set(RecordMedia.objects.filter(patient=self.patient).values_list("description", flat=True)),
            {""},
        )
        detail = self.client.get(
            self.patient_record_url(self.patient, language="en", fragment="private-media")
        )
        self.assertContains(detail, "Public case published.")
        self.assertContains(detail, "Approved public case", count=3)
        self.assertContains(detail, "Consent confirmed", count=3)
        for media in RecordMedia.objects.filter(patient=self.patient):
            self.assertContains(
                detail,
                reverse("public_case_media", kwargs={"public_id": media.public_id}),
            )
            self.assertNotContains(detail, media.file.name)
        self.assertNotContains(detail, 'href="/media/')

        RecordMedia.objects.filter(patient=self.patient).delete()
        PublicCase.objects.filter(patient=self.patient).delete()
        too_long = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="long-note.jpg"),
                note="x" * 501,
            ),
        )
        self.assertEqual(too_long.status_code, 400)
        self.assertContains(too_long, "Ensure this value does not exceed", status_code=400)
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

    def test_invalid_second_or_third_file_rolls_back_the_entire_case(self):
        invalid_second = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="valid-before.jpg"),
                after=self.synthetic_image_file(
                    name="invalid-after.gif",
                    content_type="image/gif",
                ),
            ),
        )
        self.assertContains(
            invalid_second,
            "Unsupported image file extension.",
            status_code=400,
        )
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

        invalid_third = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="valid-before-third.jpg"),
                after=self.synthetic_image_file(name="valid-after-third.jpg"),
                video=self.synthetic_video_file(
                    name="invalid-third.mp4",
                    content_type="video/quicktime",
                ),
            ),
        )
        self.assertContains(
            invalid_third,
            "Unsupported short video content type.",
            status_code=400,
        )
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

    def test_public_case_upload_reuses_extension_mime_and_size_validation(self):
        wrong_mime = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(
                    name="looks-valid.jpg",
                    content_type="application/pdf",
                ),
            ),
        )
        self.assertContains(
            wrong_mime,
            "Unsupported image content type.",
            status_code=400,
        )
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

        oversized = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=SimpleUploadedFile(
                    "oversized.jpg",
                    b"x" * (IMAGE_MAX_BYTES + 1),
                    content_type="image/jpeg",
                ),
            ),
        )
        self.assertContains(
            oversized,
            "Image file exceeds the allowed size.",
            status_code=400,
        )
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

    def test_required_public_title_and_current_patient_pii_guards(self):
        missing_title = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="missing-title.jpg"),
                title="",
            ),
        )
        self.assertContains(missing_title, "This field is required.", status_code=400)

        name_in_title = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="patient-name-title.jpg"),
                title=f"Result for {self.patient.full_name}",
            ),
        )
        self.assertContains(
            name_in_title,
            "The patient&#x27;s name or phone number cannot be published in public content.",
            status_code=400,
        )

        phone_in_note = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                before=self.synthetic_image_file(name="patient-phone-note.jpg"),
                note="Call +962 700 000 000 for this case.",
            ),
        )
        self.assertContains(
            phone_in_note,
            "The patient&#x27;s name or phone number cannot be published in public content.",
            status_code=400,
        )
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

        generic = self.client.post(
            self.url,
            self.publish_payload(
                before=self.synthetic_image_file(name="generic-patient-title.jpg"),
                title="مريض",
                note="محتوى عام غير معرّف.",
            ),
        )
        self.assertEqual(generic.status_code, 302)
        media = RecordMedia.objects.get(patient=self.patient)
        public_case = PublicCase.objects.get(patient=self.patient)
        self.assertEqual(media.public_case_role, RecordMedia.PublicCaseRole.BEFORE)
        self.assertEqual(media.title, "")
        self.assertEqual(public_case.title, "مريض")
        self.assertEqual(public_case.note, "محتوى عام غير معرّف.")

    def test_multiple_media_cover_and_internal_folder_publish_atomically(self):
        folder = self.create_media_folder(
            patient=self.patient,
            name="Internal Public Case Folder",
        )
        payload = self.publish_payload(
            folder=folder,
            title="Functional recovery overview",
            note="Public-safe short note.",
            before_files=[
                self.synthetic_image_file(name=f"before-{index}.jpg")
                for index in range(1, 4)
            ],
            after_files=[
                self.synthetic_image_file(name=f"after-{index}.png", content_type="image/png")
                for index in range(1, 3)
            ],
            video_files=[
                self.synthetic_video_file(name=f"video-{index}.mp4")
                for index in range(1, 3)
            ],
            video_cover=self.synthetic_image_file(
                name="video-cover.webp",
                content_type="image/webp",
            ),
        )

        response = self.client.post(f"{self.url}?lang=en", payload)

        self.assertEqual(response.status_code, 302)
        rows = list(RecordMedia.objects.filter(patient=self.patient).order_by("id"))
        self.assertEqual(len(rows), 8)
        self.assertEqual({row.visit_id for row in rows}, {self.visit.pk})
        self.assertEqual({row.folder_id for row in rows}, {folder.pk})
        self.assertEqual(
            {row.visibility for row in rows},
            {RecordMedia.Visibility.APPROVED_PUBLIC_CASE},
        )
        self.assertTrue(all(row.consent_confirmed and row.is_active for row in rows))
        self.assertTrue(all(row.uploaded_by_id == self.staff.pk for row in rows))
        public_case = PublicCase.objects.get(patient=self.patient)
        self.assertEqual({row.public_case_id for row in rows}, {public_case.pk})
        self.assertEqual(public_case.title, "Functional recovery overview")
        self.assertEqual(public_case.note, "Public-safe short note.")
        roles = [row.public_case_role for row in rows]
        self.assertEqual(roles.count("before"), 3)
        self.assertEqual(roles.count("after"), 2)
        self.assertEqual(roles.count("video"), 2)
        self.assertEqual(roles.count("video_cover"), 1)
        self.assertTrue(all(row.title == "" and row.description == "" for row in rows))

    def test_video_cover_rules_and_validation(self):
        cover_only = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(video_cover=self.synthetic_image_file(name="cover-only.jpg")),
        )
        self.assertContains(
            cover_only,
            "A video cover requires at least one video.",
            status_code=400,
        )
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

        invalid_cover = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                video=self.synthetic_video_file(name="cover-video.mp4"),
                video_cover=self.synthetic_image_file(
                    name="invalid-cover.gif",
                    content_type="image/gif",
                ),
            ),
        )
        self.assertContains(
            invalid_cover,
            "Unsupported image file extension.",
            status_code=400,
        )
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

        accepted = self.client.post(
            self.url,
            self.publish_payload(
                video=self.synthetic_video_file(name="accepted-cover-video.mp4"),
                video_cover=self.synthetic_image_file(name="accepted-cover.jpg"),
            ),
        )
        self.assertEqual(accepted.status_code, 302)
        roles = set(
            RecordMedia.objects.filter(patient=self.patient).values_list(
                "public_case_role",
                flat=True,
            )
        )
        self.assertEqual(roles, {"video", "video_cover"})

    def test_any_invalid_file_in_each_multiple_field_creates_zero_rows(self):
        invalid_payloads = (
            self.publish_payload(
                before_files=[
                    self.synthetic_image_file(name="valid-before-1.jpg"),
                    self.synthetic_image_file(
                        name="invalid-before-2.gif",
                        content_type="image/gif",
                    ),
                ]
            ),
            self.publish_payload(
                after_files=[
                    self.synthetic_image_file(name="valid-after-1.jpg"),
                    self.synthetic_image_file(name="valid-after-2.jpg"),
                    self.synthetic_image_file(
                        name="invalid-after-3.jpg",
                        content_type="application/pdf",
                    ),
                ]
            ),
            self.publish_payload(
                video_files=[
                    self.synthetic_video_file(name="valid-video-1.mp4"),
                    self.synthetic_video_file(
                        name="invalid-video-2.mp4",
                        content_type="video/quicktime",
                    ),
                ]
            ),
        )

        for index, payload in enumerate(invalid_payloads):
            with self.subTest(payload=index):
                response = self.client.post(f"{self.url}?lang=en", payload)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

    def test_public_case_folder_is_optional_and_patient_scoped(self):
        other_patient = self.create_patient(
            full_name="Synthetic Other Folder Owner",
            phone_raw="+962700000055",
            phone_e164="+962700000055",
        )
        other_folder = self.create_media_folder(patient=other_patient, name="Other Folder")

        rejected = self.client.post(
            f"{self.url}?lang=en",
            self.publish_payload(
                folder=other_folder,
                before=self.synthetic_image_file(name="cross-folder-case.jpg"),
            ),
        )
        self.assertContains(rejected, "Select a valid choice.", status_code=400)
        self.assertFalse(RecordMedia.objects.filter(patient=self.patient).exists())

        accepted = self.client.post(
            self.url,
            self.publish_payload(before=self.synthetic_image_file(name="unfiled-case.jpg")),
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertIsNone(RecordMedia.objects.get(patient=self.patient).folder_id)

    def test_publish_keeps_patient_portal_state_unchanged(self):
        portal_user = self.create_user(username="synthetic-public-case-portal-user")
        self.patient.user = portal_user
        self.patient.save(update_fields=["user"])
        patient_snapshot = {
            "user_id": self.patient.user_id,
            "phone_raw": self.patient.phone_raw,
            "phone_e164": self.patient.phone_e164,
        }

        response = self.client.post(
            self.url,
            self.publish_payload(video=self.synthetic_video_file()),
        )

        self.assertEqual(response.status_code, 302)
        self.patient.refresh_from_db()
        self.assertEqual(
            {
                "user_id": self.patient.user_id,
                "phone_raw": self.patient.phone_raw,
                "phone_e164": self.patient.phone_e164,
            },
            patient_snapshot,
        )
        audit = AuditLog.objects.get(metadata__action="public_case_created")
        self.assertEqual(audit.metadata["public_case_id"], PublicCase.objects.get().pk)
        self.assertEqual(audit.metadata["media_count"], 1)
        self.assertNotIn(self.patient.full_name, str(audit.metadata))


class DashboardPublicCaseLifecycleTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.patient = self.create_patient()
        self.other_patient = self.create_patient(
            full_name="Synthetic Other Lifecycle Patient",
            phone_raw="+962700000777",
            phone_e164="+962700000777",
        )
        self.reference_visit = self.create_visit(patient=self.patient)
        self.later_visit = self.create_visit(patient=self.patient)
        self.folder = self.create_media_folder(patient=self.patient, name="Lifecycle Folder")
        self.public_case = self.create_public_case(
            patient=self.patient,
            reference_visit=self.reference_visit,
            title="Lifecycle public case",
        )
        self.before = self.create_case_asset(
            self.public_case,
            role=RecordMedia.PublicCaseRole.BEFORE,
            visit=self.reference_visit,
            folder=self.folder,
        )
        self.client.force_login(self.staff)

    def create_public_case(
        self,
        *,
        patient,
        title,
        reference_visit=None,
        consent_confirmed=True,
        is_published=True,
    ):
        return PublicCase.objects.create(
            patient=patient,
            reference_visit=reference_visit,
            title=title,
            note="Synthetic public-safe lifecycle note.",
            consent_confirmed=consent_confirmed,
            is_published=is_published,
            created_by=self.staff,
        )

    def create_case_asset(
        self,
        public_case,
        *,
        role,
        visit=None,
        folder=None,
        file=None,
    ):
        media_type = (
            RecordMedia.MediaType.SHORT_VIDEO
            if role == RecordMedia.PublicCaseRole.VIDEO
            else RecordMedia.MediaType.IMAGE
        )
        return self.create_media(
            patient=public_case.patient,
            visit=visit,
            folder=folder,
            public_case=public_case,
            public_case_role=role,
            media_type=media_type,
            file=file,
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            is_active=True,
            title="",
            description="",
            uploaded_by=self.staff,
        )

    def case_url(self, route_name, public_case=None, *, patient=None, **kwargs):
        public_case = public_case or self.public_case
        patient = patient or self.patient
        return reverse(
            route_name,
            kwargs={"patient_id": patient.pk, "case_id": public_case.pk, **kwargs},
        )

    def test_manager_is_bilingual_compact_and_keeps_case_identity_outside_visit(self):
        response = self.client.get(
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.pk}),
            {"lang": "en"},
        )

        self.assertContains(response, 'id="public-cases"')
        self.assertContains(response, "Public Cases")
        self.assertContains(response, self.public_case.title)
        self.assertContains(response, "Published")
        self.assertContains(response, "Reference visit")
        for label in (
            "All media",
            "Before",
            "After",
            "Video",
            "Edit Case",
            "Add Media",
            "Manage Assets",
            "Remove from Website",
        ):
            self.assertContains(response, label)
        self.assertContains(
            response,
            f'{self.case_url("dashboard_public_case_edit")}?lang=en',
        )

    def test_lifecycle_routes_are_staff_only_owned_and_csrf_protected(self):
        edit_url = self.case_url("dashboard_public_case_edit")
        anonymous = Client().get(edit_url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn(f"{reverse('login')}?role=doctor&next=", anonymous["Location"])

        normal_client = Client()
        normal_client.force_login(self.create_user(username="lifecycle-normal-user"))
        self.assertEqual(normal_client.get(edit_url).status_code, 403)

        remove_url = self.case_url(
            "dashboard_public_case_asset_remove",
            public_id=self.before.public_id,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(csrf_client.post(remove_url).status_code, 403)
        self.before.refresh_from_db()
        self.assertEqual(self.before.public_case, self.public_case)

        other_case = self.create_public_case(
            patient=self.other_patient,
            title="Other patient lifecycle case",
        )
        self.assertEqual(
            self.client.get(
                self.case_url(
                    "dashboard_public_case_edit",
                    public_case=other_case,
                    patient=self.patient,
                )
            ).status_code,
            404,
        )

    def test_edit_updates_metadata_with_pii_and_ownership_guards_only(self):
        stored_name = self.before.file.name
        response = self.client.post(
            f'{self.case_url("dashboard_public_case_edit")}?lang=en',
            {
                "title": "Updated public-safe title",
                "note": "Updated public-safe note.",
                "reference_visit": str(self.later_visit.pk),
            },
        )

        self.assertRedirects(
            response,
            self.patient_record_url(self.patient, language="en", fragment="public-cases"),
            fetch_redirect_response=False,
        )
        self.public_case.refresh_from_db()
        self.before.refresh_from_db()
        self.assertEqual(self.public_case.title, "Updated public-safe title")
        self.assertEqual(self.public_case.note, "Updated public-safe note.")
        self.assertEqual(self.public_case.reference_visit, self.later_visit)
        self.assertEqual(self.before.file.name, stored_name)

        rejected = self.client.post(
            f'{self.case_url("dashboard_public_case_edit")}?lang=en',
            {
                "title": f"Result for {self.patient.full_name}",
                "note": "Public-safe note.",
                "reference_visit": "",
            },
        )
        self.assertContains(
            rejected,
            "The patient&#x27;s name or phone number cannot be published in public content.",
            status_code=400,
        )
        audit = AuditLog.objects.get(metadata__action="public_case_metadata_updated")
        self.assertEqual(audit.metadata, {
            "action": "public_case_metadata_updated",
            "public_case_id": self.public_case.pk,
        })

    def test_add_media_uses_later_visit_without_changing_case_identity_and_is_atomic(self):
        add_url = self.case_url("dashboard_public_case_add_media")
        response = self.client.post(
            f"{add_url}?lang=en",
            {
                "reference_visit": str(self.later_visit.pk),
                "folder": str(self.folder.pk),
                "after_images": [
                    self.synthetic_image_file(name="later-after-1.jpg"),
                    self.synthetic_image_file(name="later-after-2.jpg"),
                ],
                "videos": [self.synthetic_video_file(name="later-video.mp4")],
                "video_cover": self.synthetic_image_file(name="later-cover.jpg"),
            },
        )

        self.assertEqual(response.status_code, 302)
        rows = list(RecordMedia.objects.filter(public_case=self.public_case).order_by("pk"))
        self.assertEqual(len(rows), 5)
        new_rows = [row for row in rows if row.pk != self.before.pk]
        self.assertEqual({row.public_case_id for row in new_rows}, {self.public_case.pk})
        self.assertEqual({row.visit_id for row in new_rows}, {self.later_visit.pk})
        self.assertEqual({row.folder_id for row in new_rows}, {self.folder.pk})
        self.assertEqual(
            {row.public_case_role for row in new_rows},
            {
                RecordMedia.PublicCaseRole.AFTER,
                RecordMedia.PublicCaseRole.VIDEO,
                RecordMedia.PublicCaseRole.VIDEO_COVER,
            },
        )
        self.public_case.refresh_from_db()
        self.assertEqual(self.public_case.reference_visit, self.reference_visit)

        count_before_invalid = RecordMedia.objects.filter(public_case=self.public_case).count()
        invalid = self.client.post(
            f"{add_url}?lang=en",
            {
                "after_images": [
                    self.synthetic_image_file(name="valid-later.jpg"),
                    self.synthetic_image_file(
                        name="invalid-later.gif",
                        content_type="image/gif",
                    ),
                ],
            },
        )
        self.assertContains(invalid, "Unsupported image file extension.", status_code=400)
        self.assertEqual(
            RecordMedia.objects.filter(public_case=self.public_case).count(),
            count_before_invalid,
        )

    def test_video_cover_replacement_detaches_old_cover_without_deleting_file(self):
        video = self.create_case_asset(
            self.public_case,
            role=RecordMedia.PublicCaseRole.VIDEO,
            visit=self.later_visit,
            folder=self.folder,
        )
        old_cover = self.create_case_asset(
            self.public_case,
            role=RecordMedia.PublicCaseRole.VIDEO_COVER,
            visit=self.later_visit,
            folder=self.folder,
        )
        old_file_name = old_cover.file.name

        response = self.client.post(
            self.case_url("dashboard_public_case_add_media"),
            {"video_cover": self.synthetic_image_file(name="replacement-cover.jpg")},
        )

        self.assertEqual(response.status_code, 302)
        old_cover.refresh_from_db()
        self.assertEqual(old_cover.visibility, RecordMedia.Visibility.PRIVATE_ONLY)
        self.assertIsNone(old_cover.public_case_id)
        self.assertEqual(old_cover.public_case_role, "")
        self.assertEqual(old_cover.file.name, old_file_name)
        self.assertEqual(old_cover.folder, self.folder)
        self.assertEqual(old_cover.visit, self.later_visit)
        self.assertTrue(RecordMedia.objects.filter(pk=old_cover.pk).exists())
        self.assertEqual(
            RecordMedia.objects.filter(
                public_case=self.public_case,
                public_case_role=RecordMedia.PublicCaseRole.VIDEO_COVER,
            ).count(),
            1,
        )
        self.assertTrue(RecordMedia.objects.filter(pk=video.pk).exists())

    def test_remove_asset_and_unpublish_republish_never_delete_medical_media(self):
        stored_name = self.before.file.name
        remove_response = self.client.post(
            self.case_url(
                "dashboard_public_case_asset_remove",
                public_id=self.before.public_id,
            )
        )
        self.assertEqual(remove_response.status_code, 302)
        self.before.refresh_from_db()
        self.assertEqual(self.before.visibility, RecordMedia.Visibility.PRIVATE_ONLY)
        self.assertIsNone(self.before.public_case_id)
        self.assertEqual(self.before.public_case_role, "")
        self.assertTrue(self.before.consent_confirmed)
        self.assertEqual(self.before.folder, self.folder)
        self.assertEqual(self.before.visit, self.reference_visit)
        self.assertEqual(self.before.file.name, stored_name)

        replacement = self.create_case_asset(
            self.public_case,
            role=RecordMedia.PublicCaseRole.AFTER,
            visit=self.later_visit,
        )
        unpublish_url = self.case_url("dashboard_public_case_unpublish")
        confirmation = self.client.get(f"{unpublish_url}?lang=en")
        self.assertContains(confirmation, "Remove Case from Public Website")
        self.assertContains(
            confirmation,
            "All medical files will remain in the patient record.",
        )
        self.assertEqual(self.client.post(unpublish_url).status_code, 302)
        self.public_case.refresh_from_db()
        self.assertFalse(self.public_case.is_published)
        self.assertTrue(RecordMedia.objects.filter(pk=replacement.pk).exists())
        self.assertEqual(
            self.client.get(
                reverse("public_case_media", kwargs={"public_id": replacement.public_id})
            ).status_code,
            404,
        )

        self.assertEqual(
            self.client.post(self.case_url("dashboard_public_case_republish")).status_code,
            302,
        )
        self.public_case.refresh_from_db()
        self.assertTrue(self.public_case.is_published)

        self.public_case.is_published = False
        self.public_case.consent_confirmed = False
        self.public_case.save(update_fields=["is_published", "consent_confirmed"])
        self.client.post(self.case_url("dashboard_public_case_republish"))
        self.public_case.refresh_from_db()
        self.assertFalse(self.public_case.is_published)

    def test_merge_preserves_assets_roles_paths_and_blocks_cross_patient_or_cover_conflict(self):
        destination = self.create_public_case(
            patient=self.patient,
            title="Authoritative destination case",
        )
        destination_asset = self.create_case_asset(
            destination,
            role=RecordMedia.PublicCaseRole.AFTER,
            visit=self.reference_visit,
        )
        source_path = self.before.file.name
        destination_path = destination_asset.file.name
        response = self.client.post(
            f'{self.case_url("dashboard_public_case_merge")}?lang=en',
            {"destination_case": str(destination.pk)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PublicCase.objects.filter(pk=self.public_case.pk).exists())
        self.before.refresh_from_db()
        destination_asset.refresh_from_db()
        self.assertEqual(self.before.public_case, destination)
        self.assertEqual(self.before.public_case_role, RecordMedia.PublicCaseRole.BEFORE)
        self.assertEqual(self.before.file.name, source_path)
        self.assertEqual(destination_asset.file.name, destination_path)
        destination.refresh_from_db()
        self.assertEqual(destination.title, "Authoritative destination case")

        other_case = self.create_public_case(
            patient=self.other_patient,
            title="Cross-patient destination",
        )
        cross_source = self.create_public_case(
            patient=self.patient,
            title="Cross-patient source",
        )
        cross = self.client.post(
            self.case_url("dashboard_public_case_merge", public_case=cross_source),
            {"destination_case": str(other_case.pk)},
        )
        self.assertContains(cross, "حدد خيارا صحيحا.", status_code=400)
        self.assertTrue(PublicCase.objects.filter(pk=cross_source.pk).exists())

        cover_source = self.create_public_case(
            patient=self.patient,
            title="Cover source",
        )
        cover_destination = self.create_public_case(
            patient=self.patient,
            title="Cover destination",
        )
        self.create_case_asset(
            cover_source,
            role=RecordMedia.PublicCaseRole.VIDEO_COVER,
        )
        self.create_case_asset(
            cover_destination,
            role=RecordMedia.PublicCaseRole.VIDEO_COVER,
        )
        conflict = self.client.post(
            f'{self.case_url("dashboard_public_case_merge", public_case=cover_source)}?lang=en',
            {"destination_case": str(cover_destination.pk)},
        )
        self.assertContains(
            conflict,
            "Both cases contain a video cover. Remove or replace one cover first.",
            status_code=400,
        )
        self.assertTrue(PublicCase.objects.filter(pk=cover_source.pk).exists())
        self.assertEqual(
            AuditLog.objects.get(metadata__action="public_cases_merged").metadata[
                "media_count"
            ],
            1,
        )

    def test_linked_media_generic_edit_preserves_public_lifecycle_fields(self):
        route = reverse(
            "dashboard_media_update",
            kwargs={"patient_id": self.patient.pk, "public_id": self.before.public_id},
        )
        form_page = self.client.get(f"{route}?lang=en")
        self.assertNotContains(form_page, 'name="visibility"')
        self.assertNotContains(form_page, 'name="consent_confirmed"')

        response = self.client.post(
            route,
            {
                "folder": "",
                "title": "Internal asset label",
                "description": "Internal asset description.",
                "visibility": RecordMedia.Visibility.PRIVATE_ONLY,
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.before.refresh_from_db()
        self.assertEqual(self.before.public_case, self.public_case)
        self.assertEqual(self.before.public_case_role, RecordMedia.PublicCaseRole.BEFORE)
        self.assertEqual(self.before.visibility, RecordMedia.Visibility.APPROVED_PUBLIC_CASE)
        self.assertTrue(self.before.consent_confirmed)


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

    def test_media_edit_uses_localized_dashboard_shell_and_compact_summary(self):
        media = self.create_media(
            patient=self.patient,
            uploaded_by=self.staff,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
        )
        route = self.media_update_url(media)

        for language, direction, title, media_type, summary in (
            ("ar", "rtl", "تعديل الملف", "صورة", "ملخص الملف"),
            ("en", "ltr", "Edit Media", "Image", "Media Summary"),
        ):
            with self.subTest(language=language):
                response = self.client.get(
                    route,
                    {"lang": "en"} if language == "en" else {},
                )

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "dashboard/base.html")
                self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
                self.assertContains(response, title)
                self.assertContains(response, summary)
                self.assertContains(response, media_type)
                self.assertContains(response, str(self.staff))
                self.assertContains(response, "css/dashboard-patient-record.css")
                self.assertNotContains(response, 'class="page-hero')
                self.assertNotContains(response, 'class="booking-form')
                self.assertNotContains(response, 'enctype="multipart/form-data"')

    def test_english_media_edit_returns_to_english_private_media_section(self):
        media = self.create_media(
            patient=self.patient,
            visibility=RecordMedia.Visibility.PRIVATE_ONLY,
        )

        response = self.client.post(
            f"{self.media_update_url(media)}?lang=en",
            {
                "title": "SYNTHETIC-ENGLISH-UPDATED-MEDIA",
                "description": "SYNTHETIC-ENGLISH-UPDATED-DESCRIPTION",
                "visibility": RecordMedia.Visibility.VISIBLE_TO_PATIENT,
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            self.patient_record_url(
                self.patient,
                language="en",
                fragment="private-media",
            ),
            fetch_redirect_response=False,
        )
        media.refresh_from_db()
        self.assertEqual(media.visibility, RecordMedia.Visibility.VISIBLE_TO_PATIENT)

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
            self.patient_record_url(self.patient, fragment="private-media"),
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

    def test_generic_media_edit_cannot_create_approved_public_orphan(self):
        media = self.create_media(patient=self.patient, visibility=RecordMedia.Visibility.PRIVATE_ONLY)

        rejected_without_consent = self.client.post(
            self.media_update_url(media),
            {
                "title": media.title,
                "description": media.description,
                "visibility": RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
                "is_active": "on",
            },
        )
        media.refresh_from_db()
        rejected_with_consent = self.client.post(
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

        self.assertEqual(rejected_without_consent.status_code, 400)
        self.assertEqual(rejected_with_consent.status_code, 400)
        self.assertContains(rejected_with_consent, "حدد خيارا صحيحا.", status_code=400)
        self.assertEqual(media.visibility, RecordMedia.Visibility.PRIVATE_ONLY)
        self.assertFalse(media.consent_confirmed)
        self.assertIsNone(media.public_case_id)
        self.assertEqual(public_response.status_code, 404)
        self.assertEqual(patient_response.status_code, 404)

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


class DashboardPatientRecordResponsiveContractTests(TestCase):
    def test_record_templates_use_only_the_dashboard_shell_and_focused_stylesheet(self):
        project_root = Path(__file__).resolve().parents[2]
        template_paths = (
            "patient_record_detail.html",
            "visit_form.html",
            "note_form.html",
            "media_form.html",
            "media_folder_confirm_delete.html",
        )

        for template_name in template_paths:
            with self.subTest(template_name=template_name):
                source = (project_root / "templates" / "dashboard" / template_name).read_text(
                    encoding="utf-8"
                )

                self.assertIn('{% extends "dashboard/base.html" %}', source)
                self.assertIn("{% block dashboard_content %}", source)
                self.assertIn("dashboard-patient-record.css", source)
                self.assertNotIn('{% extends "base.html" %}', source)
                self.assertNotIn("dashboard/_dashboard_nav.html", source)
                self.assertNotIn("page-hero", source)
                self.assertNotIn("booking-form", source)
                self.assertNotIn("trust-note", source)

    def test_record_styles_define_mobile_single_column_and_overflow_contracts(self):
        css = (
            Path(__file__).resolve().parents[2]
            / "static"
            / "css"
            / "dashboard-patient-record.css"
        ).read_text(encoding="utf-8")

        for contract in (
            ".patient-record-content",
            "width: min(100%, 78rem);",
            "overflow-wrap: anywhere;",
            "word-break: break-word;",
            "flex-wrap: wrap;",
            "color: var(--dashboard-white);",
            "@media (max-width: 47.999rem)",
            "@media (max-width: 35rem)",
            "@media (max-width: 22rem)",
            ".record-patient-details",
            ".record-action-bar",
            ".record-media-actions",
            ".record-folder-organizer",
            ".record-folder-row",
            ".record-folder-create-controls",
            "grid-template-columns: minmax(0, 1fr);",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, css)

    def test_public_media_styles_keep_video_inset_contained_and_responsive(self):
        css = (
            Path(__file__).resolve().parents[2]
            / "static"
            / "css"
            / "public-closeout.css"
        ).read_text(encoding="utf-8")

        for contract in (
            ".public-case-galleries",
            "padding: 0 clamp(0.85rem, 2.5vw, 1.25rem)",
            ".public-case-video-frame",
            ".public-case-video-grid",
            "object-fit: contain;",
            "height: auto;",
            "max-height: min(70vh, 44rem);",
            "grid-template-columns: repeat(2, minmax(0, 1fr));",
            "@media (min-width: 768px)",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, css)
        self.assertNotIn("aspect-ratio: 9 / 16", css)


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


class DashboardOverviewTestMixin(DashboardRecordWorkflowMixin):
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


class DashboardPatientRecordPresentationTests(DashboardRecordWorkflowMixin, TestCase):
    def setUp(self):
        self.staff = self.create_staff()
        self.patient = self.create_patient()
        self.client.force_login(self.staff)

    def record_detail(self, *, language="ar"):
        url = reverse(
            "dashboard_patient_record_detail",
            kwargs={"patient_id": self.patient.id},
        )
        return self.client.get(url, {"lang": "en"} if language == "en" else {})

    def test_record_detail_uses_dashboard_shell_in_arabic_and_english(self):
        for language, direction, heading in (
            ("ar", "rtl", "سجل المريض"),
            ("en", "ltr", "Patient Record"),
        ):
            with self.subTest(language=language):
                response = self.record_detail(language=language)

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "dashboard/base.html")
                self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
                self.assertContains(response, 'class="dashboard-shell')
                self.assertContains(response, 'class="dashboard-sidebar"')
                self.assertContains(
                    response,
                    'class="dashboard-nav-link is-active"',
                )
                self.assertContains(response, heading)
                self.assertContains(response, "css/dashboard-patient-record.css")
                self.assertEqual(response.context["active_dashboard_nav"], "patients")
                for legacy_fragment in (
                    'class="site-shell',
                    'class="site-header',
                    'class="site-footer',
                    'class="page-hero',
                    'class="booking-steps',
                    'class="trust-note',
                ):
                    self.assertNotContains(response, legacy_fragment)

    def test_record_language_switch_and_actions_preserve_workflow_language(self):
        detail_path = reverse(
            "dashboard_patient_record_detail",
            kwargs={"patient_id": self.patient.id},
        )
        english = self.record_detail(language="en")
        arabic = self.record_detail(language="ar")

        self.assertEqual(
            arabic.context["dashboard_language_switch_url"],
            f"{detail_path}?lang=en",
        )
        self.assertEqual(english.context["dashboard_language_switch_url"], detail_path)
        self.assertEqual(
            english.context["dashboard_patients_url"],
            f"{reverse('dashboard_patient_list')}?lang=en",
        )
        for action_name in (
            "dashboard_visit_create",
            "dashboard_note_create",
            "dashboard_media_create",
        ):
            action_url = reverse(action_name, kwargs={"patient_id": self.patient.id})
            self.assertContains(english, f'href="{action_url}?lang=en"')

    def test_english_patient_list_opens_the_record_in_english(self):
        response = self.client.get(reverse("dashboard_patient_list"), {"lang": "en"})

        self.assertContains(
            response,
            f'href="{self.patient_record_url(self.patient, language="en")}"',
        )

    def test_patient_identity_card_uses_only_approved_fields_and_ltr_phone(self):
        self.patient.phone_raw = "079-INTERNAL-RAW"
        self.patient.phone_e164 = "+962790000000"
        self.patient.notes = "SYNTHETIC-PRIVATE-PATIENT-NOTES"
        self.patient.gender = Patient.Gender.FEMALE
        self.patient.save(update_fields=["phone_raw", "phone_e164", "notes", "gender"])

        response = self.record_detail(language="en")

        self.assertContains(response, "Patient Information")
        self.assertContains(response, self.patient.full_name)
        self.assertContains(response, '<dd dir="ltr">+962790000000</dd>', html=True)
        self.assertContains(response, "1990-01-01")
        self.assertContains(response, "Female")
        self.assertNotContains(response, self.patient.phone_raw)
        self.assertNotContains(response, self.patient.notes)
        self.assertNotContains(response, "Patient ID")
        self.assertNotContains(response, "data-patient-id")

    def test_record_detail_renders_all_visit_and_note_fields_without_token_leakage(self):
        appointment = self.create_appointment(self.patient)
        visit = self.create_visit(
            patient=self.patient,
            appointment=appointment,
            visit_reason="SYNTHETIC-VISIT-REASON",
            doctor_notes="SYNTHETIC-DOCTOR-NOTES",
            diagnosis_plan="SYNTHETIC-DIAGNOSIS-PLAN",
            instructions="SYNTHETIC-INSTRUCTIONS",
            follow_up_notes="SYNTHETIC-FOLLOW-UP",
            is_visible_to_patient=True,
        )
        self.create_note(
            patient=self.patient,
            visit=visit,
            note_type=ClinicalNote.NoteType.FOLLOW_UP,
            title="SYNTHETIC-CLINICAL-TITLE",
            body="SYNTHETIC-CLINICAL-BODY",
            is_visible_to_patient=False,
        )

        response = self.record_detail(language="en")

        for content in (
            appointment.visit_type.name_en,
            appointment.doctor.display_name_en,
            "SYNTHETIC-VISIT-REASON",
            "SYNTHETIC-DOCTOR-NOTES",
            "SYNTHETIC-DIAGNOSIS-PLAN",
            "SYNTHETIC-INSTRUCTIONS",
            "SYNTHETIC-FOLLOW-UP",
            "SYNTHETIC-CLINICAL-TITLE",
            "SYNTHETIC-CLINICAL-BODY",
            "Follow-up",
            "Visible to patient",
            "Private only",
        ):
            self.assertContains(response, content)
        self.assertNotContains(response, str(appointment.public_token))

    def test_record_detail_has_concise_bilingual_empty_states(self):
        arabic = self.record_detail(language="ar")
        english = self.record_detail(language="en")

        for empty_state in (
            "لا توجد زيارات بعد.",
            "لا توجد ملاحظات سريرية بعد.",
            "لا توجد وسائط خاصة بعد.",
        ):
            self.assertContains(arabic, empty_state)
        for empty_state in (
            "No visits yet.",
            "No clinical notes yet.",
            "No private media yet.",
        ):
            self.assertContains(english, empty_state)

    def test_record_collections_remain_bounded_without_per_item_queries(self):
        baseline_appointment = self.create_appointment(self.patient)
        baseline_visit = self.create_visit(patient=self.patient, appointment=baseline_appointment)
        self.create_note(patient=self.patient, visit=baseline_visit, created_by=self.staff)
        self.create_media(patient=self.patient, visit=baseline_visit, uploaded_by=self.staff)
        request = RequestFactory().get(
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id})
        )
        request.user = self.staff

        with CaptureQueriesContext(connection) as baseline_capture:
            baseline_response = dashboard_views.dashboard_patient_record_detail(
                request,
                self.patient.id,
            )
        self.assertEqual(baseline_response.status_code, 200)

        for index in range(4):
            appointment = self.create_appointment(self.patient)
            visit = self.create_visit(
                patient=self.patient,
                appointment=appointment,
                visit_reason=f"SYNTHETIC-QUERY-VISIT-{index}",
            )
            self.create_note(patient=self.patient, visit=visit, created_by=self.staff)
            self.create_media(patient=self.patient, visit=visit, uploaded_by=self.staff)

        expanded_request = RequestFactory().get(
            reverse("dashboard_patient_record_detail", kwargs={"patient_id": self.patient.id})
        )
        expanded_request.user = self.staff
        with CaptureQueriesContext(connection) as expanded_capture:
            expanded_response = dashboard_views.dashboard_patient_record_detail(
                expanded_request,
                self.patient.id,
            )
        self.assertEqual(expanded_response.status_code, 200)
        self.assertEqual(len(expanded_capture), len(baseline_capture))


class DashboardOverviewTests(DashboardOverviewTestMixin, TestCase):
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
        arabic_month_headers = arabic.content.decode().split(
            '<div class="scheduling-month-weekdays"', 1
        )[1].split("</div>", 1)[0]
        for weekday in (
            "الأحد",
            "الاثنين",
            "الثلاثاء",
            "الأربعاء",
            "الخميس",
            "الجمعة",
            "السبت",
        ):
            self.assertIn(f">{weekday}</span>", arabic_month_headers)

        english = self.scheduling(
            lang="en",
            view="month",
            date=selected_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        self.assertContains(english, '<html lang="en" dir="ltr">')
        self.assertContains(english, "Scheduling Center")
        self.assertContains(english, "Selected day")
        self.assertNotContains(english, "Working hours ≠ final availability")
        self.assertNotContains(english, "Synthetic short service")
        english_month_headers = english.content.decode().split(
            '<div class="scheduling-month-weekdays"', 1
        )[1].split("</div>", 1)[0]
        for weekday in (
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ):
            self.assertIn(f">{weekday}</span>", english_month_headers)

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
        self.assertIn('data-scheduling-customization-toggle', javascript)
        self.assertIn('setAttribute("aria-expanded"', javascript)
        self.assertIn("customizationDetails.hidden", javascript)

    def test_calendar_keeps_operational_scope_while_exposing_special_hours(self):
        self.client.force_login(self.staff)
        response = self.scheduling(lang="en")

        self.assertContains(response, "Effective hours")
        self.assertContains(response, "Appointments")
        self.assertContains(response, "Customize this day")
        self.assertContains(response, "Close full day")
        self.assertContains(response, "View Appointments")
        self.assertContains(response, "Selected day")
        self.assertNotContains(response, "Check available times")
        self.assertNotContains(response, "Select service")
        self.assertNotContains(response, "Show available times")
        self.assertNotContains(response, "Available times")
        self.assertNotContains(response, "Service availability")
        self.assertIsNone(response.context["scheduling_selected_visit_type"])
        self.assertNotContains(response, 'class="scheduling-inspector-slots"')
        rendered = response.content.decode()
        toolbar = rendered.split('<section class="scheduling-toolbar"', 1)[1].split(
            "</section>", 1
        )[0]
        self.assertNotIn("visit_type", toolbar)
        self.assertNotIn("All services", rendered)
        self.assertNotIn("Working hours ≠ final availability", rendered)
        self.assertNotIn("scheduling-availability", rendered)
        mode_actions = rendered.split(
            '<div class="scheduling-day-mode-actions"', 1
        )[1].split("</div>", 1)[0]
        self.assertEqual(mode_actions.count("scheduling-mode-action"), 2)
        self.assertNotIn("Use weekly schedule", mode_actions)
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

    def test_customize_day_starts_from_weekly_reference_and_hides_details_until_requested(self):
        target_date = self.future_date(11)
        self.create_schedule(target_date, time(9), time(17))
        self.client.force_login(self.staff)

        response = self.scheduling(lang="en", view="day", date=target_date.isoformat())
        create_form = response.context["scheduling_special_create_form"]
        self.assertEqual(create_form.initial["start_time"], time(9))
        self.assertEqual(create_form.initial["end_time"], time(17))
        self.assertContains(response, "Customize this day")
        self.assertContains(response, "Close full day")
        self.assertContains(response, "Use separate periods to represent time off between them")
        self.assertFalse(response.context["scheduling_customization_open"])
        self.assertContains(response, 'id="scheduling-customization-details" hidden')
        self.assertNotContains(response, "Using weekly schedule")
        self.assertNotContains(response, "Use weekly schedule")

        self.create_schedule_override(target_date, time(10), time(12))
        customized = self.scheduling(lang="en", view="day", date=target_date.isoformat())
        self.assertContains(customized, "Customized hours")
        self.assertContains(customized, 'id="scheduling-customization-details" hidden')
        self.assertNotContains(customized, "Use weekly schedule")

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
        self.assertNotContains(
            arabic,
            "يمنع الإغلاق الحجوزات الجديدة لذلك اليوم. عند وجود مواعيد، ستختار بوضوح إبقاءها أو إلغاءها.",
        )

        english_closures = self.scheduling(lang="en", section="closures")
        self.assertNotContains(
            english_closures,
            "A closure prevents new bookings for that date. When appointments exist, you explicitly choose whether to keep or cancel them.",
        )

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
                self.assertTrue(response.context["scheduling_customization_open"])
                self.assertNotContains(
                    response,
                    'id="scheduling-customization-details" hidden',
                    status_code=400,
                )

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
        self.assertTrue(overlap.context["scheduling_customization_open"])
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
            self.assertContains(warning, "An appointment is outside the new working hours")
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
        self.assertContains(day, "Current source")
        self.assertContains(day, "Customized hours")

        week = self.scheduling(lang="en", view="week", date=target_date.isoformat())
        week_day = next(item for item in week.context["scheduling_days"] if item["date"] == target_date)
        self.assertEqual(week_day["working_periods"], [{"start": "12:00", "end": "15:00"}])
        self.assertContains(week, "Customized")
        self.assertContains(week, 'class="scheduling-week-hours"')

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
        self.assertContains(month, ">Customized<")
        self.assertContains(month, 'class="scheduling-month" tabindex="0"')
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
            "This date is closed. Customized hours are preserved but ignored while the closure is active.",
            count=1,
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

    def test_weekly_management_is_sunday_first_uses_full_names_and_keeps_backend_mapping(self):
        self.client.force_login(self.staff)

        english = self.scheduling(lang="en", section="weekly")
        english_days = english.context["scheduling_weekly_days"]
        self.assertEqual(
            [item["weekday"] for item in english_days],
            [
                DoctorSchedule.Weekday.SUNDAY,
                DoctorSchedule.Weekday.MONDAY,
                DoctorSchedule.Weekday.TUESDAY,
                DoctorSchedule.Weekday.WEDNESDAY,
                DoctorSchedule.Weekday.THURSDAY,
                DoctorSchedule.Weekday.FRIDAY,
                DoctorSchedule.Weekday.SATURDAY,
            ],
        )
        self.assertEqual(
            [item["label"] for item in english_days],
            ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        )
        arabic = self.scheduling(section="weekly")
        self.assertEqual(
            [item["label"] for item in arabic.context["scheduling_weekly_days"]],
            ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"],
        )

        sunday = self.future_date()
        sunday += timedelta(days=(DoctorSchedule.Weekday.SUNDAY - sunday.weekday()) % 7)
        if sunday <= timezone.localdate():
            sunday += timedelta(days=7)
        created = self.client.post(
            self.action_url("dashboard_scheduling_weekly_create", language="en"),
            {"weekday": DoctorSchedule.Weekday.SUNDAY, "start_time": "09:00", "end_time": "10:00"},
        )
        self.assertEqual(created.status_code, 302)
        destination = urlsplit(created["Location"])
        self.assertEqual(parse_qs(destination.query)["section"], ["weekly"])
        self.assertEqual(destination.fragment, "weekday-sunday")
        period = DoctorSchedule.objects.get(doctor=self.doctor, start_time=time(9))
        self.assertEqual(period.weekday, 6)
        self.assertTrue(
            booking_services.generate_available_slots(
                self.short_visit,
                target_date=sunday,
                doctor=self.doctor,
            )
        )

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
            self.assertContains(warning, "There are 1 booked appointment on this date")
            self.assertEqual(
                urlsplit(warning.context["scheduling_closure_create_url"]).fragment,
                "closure-form",
            )
            self.assertContains(warning, "Allowed Conflict Summary Name")
            self.assertContains(warning, "Synthetic short service")
            self.assertContains(warning, "Confirmed")
            self.assertContains(
                warning,
                (
                    f'<time dir="ltr" datetime="{target_date.isoformat()}">'
                    f"{target_date.isoformat()}</time>"
                ),
                html=True,
            )
            self.assertContains(
                warning,
                (
                    f'href="{reverse("dashboard_scheduling")}?section=calendar&amp;'
                    f'view=day&amp;date={target_date.isoformat()}&amp;lang=en#day-management"'
                ),
            )
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
                {**payload, "closure_action": "keep"},
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

    def test_closure_cancel_choice_requires_second_confirmation_and_requeries_current_conflicts(self):
        target_date = self.future_date(8)
        first = self.create_scheduling_appointment(
            target_date,
            patient_name="First Cancellation Summary",
            status=Appointment.Status.CONFIRMED,
            booking_note="PRIVATE-CANCELLATION-NOTE",
        )
        unrelated = self.create_scheduling_appointment(
            target_date + timedelta(days=1),
            patient_name="Unrelated Date Appointment",
            status=Appointment.Status.CONFIRMED,
        )
        nonblocking = self.create_scheduling_appointment(
            target_date,
            start=time(11),
            patient_name="Already Cancelled Appointment",
            status=Appointment.Status.CANCELLED,
        )
        create_url = self.action_url("dashboard_scheduling_closure_create", language="en")
        payload = {
            "date": target_date.isoformat(),
            "reason_ar": "",
            "reason_en": "Cancel affected appointments",
        }
        self.client.force_login(self.staff)

        first_screen = self.client.post(create_url, payload)
        self.assertEqual(first_screen.status_code, 200)
        self.assertContains(first_screen, "There are 1 booked appointment on this date")
        self.assertContains(first_screen, "Close day and keep appointments")
        self.assertContains(first_screen, "Close day and cancel affected appointments")
        self.assertFalse(ClosedDay.objects.filter(doctor=self.doctor, date=target_date).exists())

        second_screen = self.client.post(create_url, {**payload, "closure_action": "cancel"})
        self.assertEqual(second_screen.status_code, 200)
        self.assertContains(second_screen, "Confirm cancellation of 1 appointment")
        self.assertContains(second_screen, "will be cancelled immediately")
        self.assertContains(second_screen, "Patient records will not be deleted")
        self.assertNotContains(second_screen, "PRIVATE-CANCELLATION-NOTE")
        self.assertNotContains(second_screen, str(first.public_token))
        first.refresh_from_db()
        self.assertEqual(first.status, Appointment.Status.CONFIRMED)
        self.assertFalse(ClosedDay.objects.filter(doctor=self.doctor, date=target_date).exists())

        second = self.create_scheduling_appointment(
            target_date,
            start=time(10),
            patient_name="New Current Conflict",
            status=Appointment.Status.ARRIVED,
        )
        with patch(
            "apps.dashboard.views.booking_operations.cancel_appointment",
            wraps=dashboard_views.booking_operations.cancel_appointment,
        ) as cancel_operation:
            final = self.client.post(
                create_url,
                {
                    **payload,
                    "closure_action": "cancel",
                    "confirm_cancellation": "yes",
                },
            )
            self.assertEqual(final.status_code, 302)
            self.assertEqual(cancel_operation.call_count, 2)

        first.refresh_from_db()
        second.refresh_from_db()
        unrelated.refresh_from_db()
        nonblocking.refresh_from_db()
        self.assertEqual(first.status, Appointment.Status.CANCELLED)
        self.assertEqual(second.status, Appointment.Status.CANCELLED)
        self.assertEqual(unrelated.status, Appointment.Status.CONFIRMED)
        self.assertEqual(nonblocking.status, Appointment.Status.CANCELLED)
        self.assertEqual(
            AppointmentStatusHistory.objects.filter(
                appointment__in=[first, second],
                new_status=Appointment.Status.CANCELLED,
                changed_by=self.staff,
            ).count(),
            2,
        )
        closure = ClosedDay.objects.get(doctor=self.doctor, date=target_date, is_active=True)
        audit = AuditLog.objects.get(
            action=AuditLog.Action.CREATE,
            model_name="ClosedDay",
            object_id=str(closure.pk),
        )
        self.assertEqual(audit.metadata["operation"], "close_and_cancel_appointments")
        self.assertEqual(audit.metadata["cancelled_appointment_count"], 2)
        metadata_text = str(audit.metadata)
        self.assertNotIn("First Cancellation Summary", metadata_text)
        self.assertNotIn("New Current Conflict", metadata_text)
        self.assertNotIn("PRIVATE-CANCELLATION-NOTE", metadata_text)
        self.assertEqual(urlsplit(final["Location"]).fragment, "closures-list")

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

    def test_service_create_deactivate_warning_reactivate_public_visibility_and_audit(self):
        self.client.force_login(self.staff)
        create_url = self.action_url("dashboard_scheduling_service_create", language="en")

        for payload in (
            {"name_ar": "", "name_en": "New service", "duration_minutes": "30"},
            {"name_ar": "خدمة جديدة", "name_en": "", "duration_minutes": "30"},
            {"name_ar": "خدمة جديدة", "name_en": "New service", "duration_minutes": "0"},
            {"name_ar": "خدمة جديدة", "name_en": "New service", "duration_minutes": "invalid"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(create_url, payload).status_code, 400)

        created = self.client.post(
            create_url,
            {
                "name_ar": "خدمة مضافة تجريبية",
                "name_en": "Synthetic added service",
                "duration_minutes": "25",
            },
        )
        self.assertEqual(created.status_code, 302)
        service = VisitType.objects.get(name_en="Synthetic added service")
        self.assertEqual(service.doctor, self.doctor)
        self.assertTrue(service.is_active)
        self.assertEqual(service.duration_minutes, 25)
        self.assertEqual(urlsplit(created["Location"]).fragment, f"service-{service.pk}")
        self.assertContains(self.client.get(reverse("book_en")), service.name_en)
        create_audit = AuditLog.objects.get(
            action=AuditLog.Action.CREATE,
            model_name="VisitType",
            object_id=str(service.pk),
        )
        self.assertEqual(create_audit.metadata["active"], True)

        appointment_day = self.future_date(9)
        appointment = self.create_scheduling_appointment(
            appointment_day,
            visit_type=service,
            patient_name="Safe Service Conflict Name",
            status=Appointment.Status.CONFIRMED,
            booking_note="PRIVATE-SERVICE-BOOKING-NOTE",
        )
        appointment.patient.phone_raw = "+962799999988"
        appointment.patient.phone_e164 = "+962799999988"
        appointment.patient.save(update_fields=["phone_raw", "phone_e164"])
        deactivate_url = self.action_url(
            "dashboard_scheduling_service_deactivate",
            language="en",
            visit_type_id=service.pk,
        )
        warning = self.client.post(deactivate_url)
        self.assertEqual(warning.status_code, 200)
        self.assertContains(warning, "Future appointments use this service")
        self.assertEqual(
            urlsplit(warning.context["scheduling_service_confirmation"]["action_url"]).fragment,
            "service-warning",
        )
        self.assertContains(warning, "Safe Service Conflict Name")
        self.assertNotContains(warning, "+962799999988")
        self.assertNotContains(warning, "PRIVATE-SERVICE-BOOKING-NOTE")
        self.assertNotContains(warning, str(appointment.public_token))
        service.refresh_from_db()
        self.assertTrue(service.is_active)

        deactivated = self.client.post(
            deactivate_url,
            {"confirm_service_deactivation": "yes"},
        )
        self.assertEqual(deactivated.status_code, 302)
        service.refresh_from_db()
        appointment.refresh_from_db()
        self.assertFalse(service.is_active)
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertTrue(Appointment.objects.filter(pk=appointment.pk).exists())
        self.assertNotContains(self.client.get(reverse("book_en")), service.name_en)
        deactivate_audit = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE,
            model_name="VisitType",
            object_id=str(service.pk),
        ).latest("created_at")
        self.assertEqual(deactivate_audit.metadata, {"old_active": True, "new_active": False})
        self.assertEqual(
            self.client.post(f"/dashboard/scheduling/services/{service.pk}/delete/").status_code,
            404,
        )

        reactivated = self.client.post(
            self.action_url(
                "dashboard_scheduling_service_reactivate",
                language="en",
                visit_type_id=service.pk,
            )
        )
        self.assertEqual(reactivated.status_code, 302)
        service.refresh_from_db()
        self.assertTrue(service.is_active)
        self.assertContains(self.client.get(reverse("book_en")), service.name_en)
        reactivate_audit = AuditLog.objects.filter(
            action=AuditLog.Action.UPDATE,
            model_name="VisitType",
            object_id=str(service.pk),
        ).latest("created_at")
        self.assertEqual(reactivate_audit.metadata, {"old_active": False, "new_active": True})

    def test_booking_rule_copy_is_clear_and_slot_interval_minimum_is_unchanged(self):
        self.client.force_login(self.staff)
        english = self.scheduling(lang="en", section="rules")
        self.assertContains(english, "Allow booking up to")
        self.assertContains(english, "Days in advance")
        self.assertContains(english, "Appointment slots start every")
        self.assertNotContains(english, "Buffer")
        arabic = self.scheduling(section="rules")
        self.assertContains(arabic, "السماح بالحجز حتى")
        self.assertContains(arabic, "يوماً مقدماً")
        self.assertContains(arabic, "تبدأ أوقات الحجز كل")

        url = self.action_url("dashboard_scheduling_rules_update", language="en")
        rejected = self.client.post(
            url,
            self.rules_payload(booking_slot_interval_minutes="0"),
        )
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.post(
            url,
            self.rules_payload(booking_slot_interval_minutes="1"),
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(booking_services.get_booking_settings().slot_interval_minutes, 1)
        self.assertEqual(urlsplit(accepted["Location"]).fragment, "booking-rules")

    def test_same_page_navigation_preserves_workflow_context_and_fragments(self):
        target_date = self.future_date(10)
        self.client.force_login(self.staff)
        calendar = self.scheduling(
            lang="en",
            section="calendar",
            view="month",
            date=target_date.isoformat(),
            visit_type=self.short_visit.pk,
        )
        for context_key, fragment in (
            ("scheduling_previous_url", "calendar"),
            ("scheduling_today_url", "calendar"),
            ("scheduling_next_url", "calendar"),
            ("scheduling_current_url", "day-management"),
        ):
            destination = urlsplit(calendar.context[context_key])
            query = parse_qs(destination.query)
            self.assertEqual(query["lang"], ["en"])
            self.assertEqual(query["view"], ["month"])
            self.assertEqual(query["visit_type"], [str(self.short_visit.pk)])
            self.assertEqual(destination.fragment, fragment)
        for tab in calendar.context["scheduling_view_tabs"]:
            self.assertEqual(urlsplit(tab["url"]).fragment, "calendar-toolbar")

        duration = self.client.post(
            self.action_url(
                "dashboard_scheduling_service_duration",
                language="en",
                visit_type_id=self.short_visit.pk,
            ),
            {"duration_minutes": "20"},
        )
        self.assertEqual(urlsplit(duration["Location"]).fragment, f"service-{self.short_visit.pk}")
        self.assertEqual(
            parse_qs(urlsplit(duration["Location"]).query)["section"],
            ["services"],
        )

        special = self.client.post(
            self.special_action_url(
                "dashboard_scheduling_special_create",
                target_date,
            ),
            {
                "date": target_date.isoformat(),
                "start_time": "12:00",
                "end_time": "13:00",
                "reason_ar": "",
                "reason_en": "Context preservation",
            },
        )
        special_destination = urlsplit(special["Location"])
        special_query = parse_qs(special_destination.query)
        self.assertEqual(special_query["lang"], ["en"])
        self.assertEqual(special_query["view"], ["day"])
        self.assertEqual(special_query["date"], [target_date.isoformat()])
        self.assertEqual(special_destination.fragment, "day-management")

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
        inactive_security_service = VisitType.objects.create(
            doctor=self.doctor,
            name_ar="خدمة أمنية متوقفة",
            name_en="Inactive security service",
            duration_minutes=20,
            is_active=False,
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
                "service-create",
                self.action_url("dashboard_scheduling_service_create", language="en"),
                {
                    "name_ar": "خدمة اختبار أمني",
                    "name_en": "Security route service",
                    "duration_minutes": "25",
                },
            ),
            (
                "service-deactivate",
                self.action_url(
                    "dashboard_scheduling_service_deactivate",
                    language="en",
                    visit_type_id=self.long_visit.pk,
                ),
                {},
            ),
            (
                "service-reactivate",
                self.action_url(
                    "dashboard_scheduling_service_reactivate",
                    language="en",
                    visit_type_id=inactive_security_service.pk,
                ),
                {},
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
            ".scheduling-day-mode-actions",
            ".scheduling-customization-details",
            ".scheduling-service-create-fields",
            ".dashboard-shell .scheduling-appointments-link",
            ".dashboard-shell .scheduling-button",
            "@media (max-width: 63.999rem)",
            "@media (max-width: 47.999rem)",
            "@media (max-width: 35rem)",
            ":focus-visible",
            "min-width: 0",
            "overflow-wrap: anywhere",
            "overflow-x: auto",
            "14px",
        ):
            self.assertIn(contract, stylesheet)
        self.assertIn(
            "calc(3rem + var(--appointment-duration) * 0.035rem)",
            stylesheet,
        )
