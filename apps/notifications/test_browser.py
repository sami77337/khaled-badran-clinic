import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class PushRuntimeTests(SimpleTestCase):
    def test_service_worker_and_control_runtime(self):
        result = subprocess.run(["node", "--test", "--test-reporter=tap", str(Path(__file__).parent / "js_tests/push_runtime_test.js")],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())


class PushLayoutTests(TestCase):
    def test_dashboard_control_ar_en_mobile_and_desktop(self):
        candidates = [os.environ.get("KBC_QA_BROWSER"), shutil.which("google-chrome"), shutil.which("chromium"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"]
        browser = next((value for value in candidates if value and Path(value).is_file()), None)
        if not browser:
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Chromium is required for dashboard phone notification layout QA")
            self.skipTest("Install Chromium or set KBC_QA_BROWSER")
        self.client.force_login(get_user_model().objects.create_user(username="synthetic-push-layout", is_staff=True))
        pages = {}
        for language in ("ar", "en"):
            response = self.client.get(reverse("dashboard_home") + f"?lang={language}")
            self.assertEqual(response.status_code, 200)
            pages[language] = response.content.decode()
        with TemporaryDirectory(prefix="kbc-push-layout-") as directory:
            fixture = Path(directory) / "pages.json"
            fixture.write_text(json.dumps(pages), encoding="utf-8")
            result = subprocess.run(["node", str(Path(__file__).parent / "js_tests/push_layout_test.js"),
                browser, str(fixture), str(settings.BASE_DIR)], capture_output=True, text=True, encoding="utf-8", timeout=90)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
