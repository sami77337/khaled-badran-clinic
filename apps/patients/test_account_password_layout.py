"""Mobile RTL/LTR regression against rendered Django pages and installed Chromium."""

import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


class AccountPasswordLayoutTests(TestCase):
    def test_password_toggle_geometry_and_behavior_in_rtl_and_ltr(self):
        candidates = [
            os.environ.get("KBC_QA_BROWSER"),
            shutil.which("google-chrome"),
            shutil.which("chromium"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        ]
        browser = next(
            (item for item in candidates if item and Path(item).is_file()), None
        )
        if not browser or not shutil.which("node"):
            if (
                os.environ.get("CI") == "true"
                or os.environ.get("GITHUB_ACTIONS") == "true"
            ):
                self.fail("Node and Chromium are required for password layout QA in CI")
            self.skipTest(
                "Install Chromium or set KBC_QA_BROWSER for password layout QA"
            )
        cache.clear()
        self.addCleanup(cache.clear)
        phone = "+12025550101"
        get_user_model().objects.create_user(
            username=phone, password="Synthetic-layout-pass-778!"
        )
        with override_settings(PATIENT_ACCOUNT_OTP_SENDER=Mock(return_value=True)):
            with patch(
                "apps.patients.account_otp.generate_otp_code", return_value="123456"
            ):
                self.client.post(
                    reverse("patient_portal_account_recovery_en"),
                    {"phone": phone},
                    follow=True,
                )
            self.client.post(
                reverse("patient_portal_account_recovery_en"),
                {"action": "verify", "otp": "123456"},
            )
        pages = {}
        for language in ("ar", "en"):
            suffix = "_en" if language == "en" else ""
            for name, route, query in (
                ("login", "login", ""),
                ("register", "patient_portal_register", ""),
                ("recovery", "patient_portal_account_recovery", "?reset=1"),
            ):
                response = self.client.get(reverse(route + suffix) + query)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "css/auth-closeout.css")
                self.assertContains(response, "data-password-toggle")
                self.assertContains(response, 'dir="ltr"')
                pages[f"{name}-{language}"] = response.content.decode()
        with TemporaryDirectory(prefix="kbc-account-password-layout-") as directory:
            fixture = Path(directory) / "pages.json"
            fixture.write_text(json.dumps(pages), encoding="utf-8")
            result = subprocess.run(
                [
                    "node",
                    str(
                        settings.BASE_DIR
                        / "apps/patients/js_tests/account_password_layout_test.js"
                    ),
                    browser,
                    str(fixture),
                    str(settings.BASE_DIR),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=150,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
