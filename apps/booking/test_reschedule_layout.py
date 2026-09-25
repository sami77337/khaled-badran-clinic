"""Chromium QA of real Django-rendered rescheduling pages, with synthetic data."""

import json
from datetime import timedelta
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.booking import rescheduling
from apps.booking.test_patient_rescheduling import RescheduleFixtureMixin
from apps.core.models import SystemSetting
from apps.patients.models import Patient


class PatientRescheduleLayoutTests(RescheduleFixtureMixin, TestCase):
    def test_rendered_ar_en_flow_at_required_widths(self):
        candidates = (
            os.environ.get("KBC_QA_BROWSER"), shutil.which("google-chrome"), shutil.which("chromium"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        )
        browser = next((item for item in candidates if item and Path(item).is_file()), None)
        if not browser or not shutil.which("node"):
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Node and Chromium are required for reschedule layout QA in CI")
            self.skipTest("Node and Chromium are required for reschedule layout QA")
        public_patient = Patient.objects.create(
            full_name="PRIVATE-PUBLIC-BOOKING-PATIENT-SENTINEL",
            phone_raw="+962790000088",
            phone_e164="+962790000088",
        )
        public_appointment = self.create_appointment(
            doctor=self.doctor,
            visit_type=self.visit_type,
            patient=public_patient,
            starts_at=self.target + timedelta(days=1),
        )
        public_appointment.booking_note = "PRIVATE-PUBLIC-BOOKING-NOTE-SENTINEL"
        public_appointment.contact_phone_raw = "0790000088"
        public_appointment.contact_phone_e164 = "+962790000088"
        public_appointment.whatsapp_phone_raw = "0790000088"
        public_appointment.whatsapp_phone_e164 = "+962790000088"
        public_appointment.save()
        pages = {}
        for language in ("ar", "en"):
            for state, route, query in (
                ("slots", "patient_reschedule", {}),
                ("selected", "patient_reschedule", {"starts_at": self.target.isoformat()}),
                ("confirm", "patient_reschedule_confirm", {"starts_at": self.target.isoformat()}),
            ):
                response = self.client.get(self.url(route, language=language), query)
                self.assertEqual(response.status_code, 200)
                pages[f"{state}-{language}"] = response.content.decode()
            response = self.client.get(self.url(token="invalid", language=language))
            self.assertEqual(response.status_code, 400)
            pages[f"error-{language}"] = response.content.decode()
            setting = SystemSetting.objects.create(key=SystemSetting.BOOKING_ENABLED, value="false")
            pages[f"empty-{language}"] = self.client.get(self.url(language=language)).content.decode()
            setting.delete()
            # Exercise the shared template's original public booking branch too.
            pages[f"booking-{language}"] = self.client.get(
                reverse("booking_slots_en" if language == "en" else "booking_slots"),
                {"visit_type": self.visit_type.pk},
            ).content.decode()

            confirm_response = self.client.get(
                reverse("booking_confirm_en" if language == "en" else "booking_confirm"),
                {"visit_type": self.visit_type.pk, "starts_at": self.target.isoformat()},
            )
            self.assertEqual(confirm_response.status_code, 200)
            pages[f"booking-confirm-{language}"] = confirm_response.content.decode()

            success_response = self.client.get(
                reverse(
                    "booking_success_en" if language == "en" else "booking_success",
                    kwargs={"public_token": public_appointment.public_token},
                )
            )
            self.assertEqual(success_response.status_code, 200)
            self.assertIn("no-store", success_response.headers.get("Cache-Control", ""))
            success_html = success_response.content.decode()
            for private_value in (
                public_patient.full_name,
                public_patient.phone_e164,
                public_appointment.booking_note,
                public_appointment.contact_phone_e164,
                public_appointment.whatsapp_phone_e164,
            ):
                self.assertNotIn(private_value, success_html)
            pages[f"booking-success-{language}"] = success_html
        self.assertEqual(self.post().status_code, 302)
        self.appointment.refresh_from_db()
        receipt = rescheduling.make_reschedule_receipt(self.appointment)
        for language in ("ar", "en"):
            pages[f"success-{language}"] = self.client.get(
                self.url("patient_reschedule_success", token=receipt, language=language),
            ).content.decode()
        assets = {}
        for html in pages.values():
            for url in re.findall(r'(?:href|src)="(/static/[^"?]+)', html):
                resolved = finders.find(url.removeprefix("/static/"))
                if resolved:
                    assets[url] = str(Path(resolved).resolve())
        with TemporaryDirectory(prefix="kbc-reschedule-layout-") as directory:
            fixture = Path(directory) / "pages.json"
            fixture.write_text(json.dumps({"pages": pages, "assets": assets}), encoding="utf-8")
            result = subprocess.run(
                ["node", str(settings.BASE_DIR / "apps/booking/js_tests/reschedule_layout_test.js"), browser, str(fixture)],
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
