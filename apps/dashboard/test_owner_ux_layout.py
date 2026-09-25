"""Chromium QA using isolated Django-rendered synthetic fixtures."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from apps.clinic.models import Doctor
from apps.core.models import DoctorPageSection


class OwnerUXLayoutTests(TestCase):
    def test_responsive_bilingual_pages_and_install_runtime(self):
        candidates = (
            os.environ.get("KBC_QA_BROWSER"),
            shutil.which("google-chrome"),
            shutil.which("chromium"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        )
        browser = next(
            (item for item in candidates if item and Path(item).is_file()), None
        )
        if not browser or not shutil.which("node"):
            if os.environ.get("CI") == "true":
                self.fail("Node and Chromium are required for owner UX QA in CI")
            self.skipTest("Node and Chromium unavailable for rendered verification")
        staff = get_user_model().objects.create_superuser(
            username="synthetic-owner-layout"
        )
        doctor = Doctor.objects.create(
            full_name_ar="طبيب تجريبي", full_name_en="Synthetic Doctor"
        )
        self.client.force_login(staff)
        pages = {}
        for language in ("ar", "en"):
            for route in ("home", "doctor", "services", "contact"):
                pages[f"{route}-{language}"] = self.client.get(
                    reverse(route + ("_en" if language == "en" else ""))
                ).content.decode()
            for name, route, kwargs in (
                ("dashboard-home", "dashboard_home", {}),
                ("scheduling", "dashboard_scheduling", {}),
                ("appointment-messages", "dashboard_appointment_message_settings", {}),
                ("appointment-follow-up", "dashboard_appointment_follow_up", {}),
                ("content", "dashboard_content", {}),
                ("home-form", "dashboard_public_copy", {"page": "home"}),
                ("section-form", "dashboard_doctor_section_new", {}),
                ("bio-form", "dashboard_doctor_bio", {}),
                ("password", "dashboard_password_change", {}),
            ):
                pages[f"{name}-{language}"] = self.client.get(
                    reverse(route, kwargs=kwargs) + f"?lang={language}"
                ).content.decode()
            pages[f"password-errors-{language}"] = self.client.post(
                reverse("dashboard_password_change") + f"?lang={language}",
                {
                    "old_password": "bad",
                    "new_password1": "short",
                    "new_password2": "different",
                },
            ).content.decode()
        for mode in DoctorPageSection.Presentation.values:
            DoctorPageSection.objects.create(
                doctor=doctor,
                title_ar=f"قسم تجريبي {mode}",
                title_en=f"Synthetic {mode}",
                content_ar="نص تجريبي " * 12 + "\n" + "س" * 140,
                content_en="Synthetic text " * 12 + "\n" + "W" * 140,
                presentation=mode,
            )
        for language in ("ar", "en"):
            pages[f"custom-modes-{language}"] = self.client.get(
                reverse("doctor" + ("_en" if language == "en" else ""))
            ).content.decode()
        assets = {}
        for html in pages.values():
            for url in re.findall(r'(?:href|src)="(/static/[^"?]+)', html):
                resolved = finders.find(url.removeprefix("/static/"))
                if resolved:
                    assets[url] = str(Path(resolved).resolve())
        # Local stylesheet font URLs are loaded too, keeping viewport measurements realistic.
        for file in (settings.BASE_DIR / "static/fonts").rglob("*.woff2"):
            assets[
                "/static/" + file.relative_to(settings.BASE_DIR / "static").as_posix()
            ] = str(file)
        assets["/sw.js"] = str(settings.BASE_DIR / "static/sw.js")
        with TemporaryDirectory(prefix="kbc-owner-ux-") as directory:
            fixture = Path(directory) / "pages.json"
            fixture.write_text(
                json.dumps({"pages": pages, "assets": assets}), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    "node",
                    str(settings.BASE_DIR / "apps/dashboard/js_tests/owner_ux_test.js"),
                    browser,
                    str(fixture),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
