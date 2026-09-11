"""Real Django pages and installed Chromium; only isolated synthetic records."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib import admin
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from apps.core.models import PublicReview
from apps.patients.models import Consultation, ConsultationAttachment, ConsultationNotification, Patient
from apps.records.models import ClinicalNote, PublicCase, PublicCaseMedia, RecordMedia, RecordMediaFolder


class FinalCloseoutLayoutTests(TestCase):
    def test_native_upload_controls_in_arabic_and_english(self):
        candidates = [
            os.environ.get("KBC_QA_BROWSER"), shutil.which("google-chrome"), shutil.which("chromium"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        ]
        browser = next((item for item in candidates if item and Path(item).is_file()), None)
        if not browser or not shutil.which("node"):
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Node and Chromium are required for upload layout QA in CI")
            self.skipTest("Install Chromium or set KBC_QA_BROWSER for upload layout QA")
        user = get_user_model().objects.create_user(username="synthetic-upload-patient")
        staff = get_user_model().objects.create_user(
            username="synthetic-upload-staff", is_staff=True, is_superuser=True,
        )
        patient = Patient.objects.create(user=user, full_name="Synthetic upload patient")
        consultation = Consultation.objects.create(patient=patient, question="Synthetic upload question")
        public_case = PublicCase.objects.create(title="Synthetic upload case", created_by=staff)
        pages = {}
        cache.clear()
        self.addCleanup(cache.clear)

        def capture(name, url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, 'css/file-upload.css')
            self.assertContains(response, 'type="file"')
            pages[name] = response.content.decode()

        for language in ("ar", "en"):
            suffix = "_en" if language == "en" else ""
            self.client.force_login(user)
            capture(f"upload-patient-{language}", reverse("patient_portal_consultation_new" + suffix))
            self.client.force_login(staff)
            for name, route, kwargs in (
                ("record", "dashboard_media_create", {"patient_id": patient.pk}),
                ("case-create", "dashboard_public_case_create", {}),
                ("case-add", "dashboard_public_case_add_media", {"case_id": public_case.pk}),
                ("staff-audio", "dashboard_consultation_detail", {"public_id": consultation.public_id}),
            ):
                capture(f"upload-{name}-{language}", reverse(route, kwargs=kwargs) + f"?lang={language}")
            with translation.override(language):
                for model in ("recordmedia", "publiccasemedia"):
                    capture(f"upload-admin-{model}-{language}", reverse(f"admin:records_{model}_add"))
            self.client.logout()
            cache.clear()
            entry = reverse("guest_consultation_entry" + suffix)
            with override_settings(GUEST_CONSULTATION_OTP_SENDER=lambda *args: True):
                with patch("apps.patients.transient_services.generate_otp_code", return_value="123456"):
                    self.assertEqual(self.client.post(entry, {
                        "action": "send", "phone": "+12025550101",
                    }).status_code, 302)
                self.assertEqual(self.client.post(entry, {
                    "action": "verify", "code": "123456",
                }).status_code, 302)
            capture(f"upload-guest-{language}", entry)

        with TemporaryDirectory(prefix="kbc-upload-layout-") as directory:
            fixture = Path(directory) / "pages.json"
            fixture.write_text(json.dumps(pages), encoding="utf-8")
            result = subprocess.run(
                ["node", str(settings.BASE_DIR / "apps/patients/js_tests/closeout_layout_test.js"),
                 browser, str(fixture), str(settings.BASE_DIR), str(Path(admin.__file__).parent / "static")],
                capture_output=True, text=True, encoding="utf-8", timeout=240,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())

    def test_notifications_reviews_and_folder_text_geometry(self):
        # Prefer stable Chrome over the slower Chromium launcher on hosted Linux.
        candidates = [
            os.environ.get("KBC_QA_BROWSER"), shutil.which("google-chrome"), shutil.which("chromium"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        ]
        browser = next((item for item in candidates if item and Path(item).is_file()), None)
        if not browser or not shutil.which("node"):
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Node and Chromium are required for closeout layout QA in CI")
            self.skipTest("Install Chromium or set KBC_QA_BROWSER for closeout layout QA")
        user = get_user_model().objects.create_user(username="synthetic-closeout-patient")
        staff = get_user_model().objects.create_user(username="synthetic-closeout-staff", is_staff=True)
        patient = Patient.objects.create(user=user, full_name="Synthetic closeout patient")
        for _ in range(9):
            consultation = Consultation.objects.create(patient=patient, question="Synthetic layout question")
            for recipient, kind in (
                (user, ConsultationNotification.Kind.CONSULTATION_REPLIED),
                (staff, ConsultationNotification.Kind.NEW_CONSULTATION),
            ):
                ConsultationNotification.objects.create(recipient=recipient, consultation=consultation, kind=kind)
        for language in ("ar", "en"):
            PublicReview.objects.create(
                reviewer_name="تقييم بلا نص" if language == "ar" else "Rating-only reviewer",
                body="", rating=4, language=language, source=PublicReview.Source.GOOGLE,
                is_approved_for_publication=True, is_active=True,
            )
            PublicReview.objects.create(
                reviewer_name=("س" if language == "ar" else "W") * 160,
                body="https://example.test/" + "x" * 400 + " " + "س" * 400,
                rating=5, language=language, source=PublicReview.Source.OTHER,
                is_approved_for_publication=True, is_active=True,
            )
        with TemporaryDirectory(prefix="kbc-closeout-layout-") as directory:
            with override_settings(
                PRIVATE_MEDIA_ROOT=Path(directory) / "private",
                PUBLIC_CASE_MEDIA_ROOT=Path(directory) / "public-cases",
            ):
                long_text = "W" * 180 + " " + "س" * 180 + " https://example.test/" + "x" * 240
                folder = RecordMediaFolder.objects.create(patient=patient, name="W" * 120, created_by=staff)
                RecordMedia.objects.create(
                    patient=patient, folder=folder, media_type=RecordMedia.MediaType.IMAGE,
                    file=SimpleUploadedFile("synthetic.jpg", b"synthetic-media", content_type="image/jpeg"),
                    visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
                    title="W" * 180, description=long_text,
                )
                ClinicalNote.objects.create(patient=patient, title="W" * 180, body=long_text, is_visible_to_patient=True)
                ConsultationAttachment.objects.create(
                    consultation=consultation, file_category="image",
                    file=SimpleUploadedFile("W" * 170 + ".jpg", b"synthetic-media", content_type="image/jpeg"),
                )
                public_case = PublicCase.objects.create(
                    title="W" * 180, note=long_text, detail_note=long_text, consent_confirmed=True,
                )
                PublicCaseMedia.objects.create(
                    public_case=public_case, role="primary", media_type="image", consent_confirmed=True,
                    file=SimpleUploadedFile("synthetic.jpg", b"synthetic-media", content_type="image/jpeg"),
                )
                public_case.is_published = True
                public_case.save()
                pages = {}

                def add_page(name, url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200, url)
                    pages[name] = response.content.decode()

                for language in ("ar", "en"):
                    suffix = "_en" if language == "en" else ""
                    self.client.logout()
                    for route in ("home", "reviews", "contact"):
                        add_page(f"{route}-{language}", reverse(route + suffix))
                    add_page(f"case-detail-{language}", reverse("public_case_detail" + suffix, kwargs={"case_id": public_case.pk}))
                    self.client.force_login(user)
                    for name, route in (("medical-records", "patient_portal_medical_records"), ("link", "patient_portal_link_appointment")):
                        add_page(f"{name}-{language}", reverse(route + suffix))
                    invalid_link = self.client.post(reverse("patient_portal_link_appointment" + suffix), {})
                    self.assertEqual(invalid_link.status_code, 200)
                    pages[f"link-errors-{language}"] = invalid_link.content.decode()
                    add_page(f"consultation-patient-{language}", reverse(
                        "patient_portal_consultation_detail" + suffix, kwargs={"public_id": consultation.public_id},
                    ))
                    add_page(f"notifications-public-{language}", reverse("home" + suffix))
                    add_page(f"notifications-patient-{language}", reverse("patient_portal_dashboard" + suffix))
                    self.client.force_login(staff)
                    add_page(f"notifications-staff-{language}", reverse("dashboard_home") + f"?lang={language}")
                    add_page(f"record-{language}", reverse(
                        "dashboard_patient_record_detail", kwargs={"patient_id": patient.pk},
                    ) + f"?lang={language}")
                    self.assertIn(folder.name, pages[f"record-{language}"])
                    add_page(f"folder-delete-{language}", reverse(
                        "dashboard_media_folder_delete", kwargs={"patient_id": patient.pk, "folder_id": folder.pk},
                    ) + f"?lang={language}")
                    add_page(f"consultation-staff-{language}", reverse(
                        "dashboard_consultation_detail", kwargs={"public_id": consultation.public_id},
                    ) + f"?lang={language}")
                fixture = Path(directory) / "pages.json"
                fixture.write_text(json.dumps(pages), encoding="utf-8")
                result = subprocess.run(
                    ["node", str(settings.BASE_DIR / "apps/patients/js_tests/closeout_layout_test.js"),
                     browser, str(fixture), str(settings.BASE_DIR)],
                    capture_output=True, text=True, encoding="utf-8", timeout=240,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                print(result.stdout.strip())
