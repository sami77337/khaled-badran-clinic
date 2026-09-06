"""Render real pages with their real CSS in an installed Chromium browser.

No browser package or download is required. Set KBC_QA_BROWSER to override the
Chrome/Edge executable. The test database supplies an isolated patient account.
"""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .tests import PatientPortalTestMixin


class PatientPhonePickerLayoutTests(PatientPortalTestMixin, TestCase):
    def test_portal_matches_login_computed_mobile_layout(self):
        candidates = [
            os.environ.get("KBC_QA_BROWSER"),
            shutil.which("chromium"),
            shutil.which("google-chrome"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        ]
        browser = next((p for p in candidates if p and Path(p).is_file()), None)
        if not browser:
            self.skipTest("Install Chromium or set KBC_QA_BROWSER for computed layout QA")

        with TemporaryDirectory(prefix="kbc-phone-layout-") as directory:
            pages = {}
            for language in ("ar", "en"):
                suffix = "_en" if language == "en" else ""
                self.client.logout()
                for name, route in (("login", "login"), ("register", "patient_portal_register")):
                    response = self.client.get(reverse(route + suffix))
                    self.assertEqual(response.status_code, 200)
                    pages[f"{name}-{language}"] = response.content.decode()
                self.client.force_login(self.create_user(username=f"layout-{language}"))
                for name, route in (
                    ("link", "patient_portal_link_appointment"),
                    ("phone", "patient_portal_password_change"),
                ):
                    response = self.client.get(reverse(route + suffix))
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "css/auth-phone.css")
                    self.assertNotContains(response, "css/booking.css")
                    self.assertContains(response, "patient-form patient-phone-picker")
                    pages[f"{name}-{language}"] = response.content.decode()
            fixture = Path(directory) / "pages.json"
            # Optional local comparison with the owner's immutable reference SHA.
            # Only the named CSS file is read; no checkout or worktree is needed.
            baseline = os.environ.get("KBC_QA_BASELINE")
            if baseline:
                pages["baseline-auth.css"] = subprocess.check_output(
                    ["git", "show", f"{baseline}:static/css/auth.css"],
                    cwd=settings.BASE_DIR, encoding="utf-8",
                )
                for language in ("ar", "en"):
                    pages[f"before-login-{language}"] = re.sub(
                        r'<link[^>]+css/auth-phone\.css[^>]+>', "",
                        pages[f"login-{language}"],
                    ).replace("/static/css/auth.css", "/baseline-auth.css")
                    pages[f"before-link-{language}"] = pages[f"link-{language}"].replace(
                        "css/auth-phone.css", "css/booking.css",
                    ).replace("patient-form patient-phone-picker", "patient-form booking-form").replace(
                        "dashboard-content patient-page-content", "dashboard-content patient-page-content page-booking",
                    )
            fixture.write_text(json.dumps(pages), encoding="utf-8")
            result = subprocess.run(
                ["node", str(settings.BASE_DIR / "apps/patients/js_tests/phone_picker_layout_test.js"),
                 browser, str(fixture), str(settings.BASE_DIR)],
                capture_output=True, text=True, encoding="utf-8", timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
