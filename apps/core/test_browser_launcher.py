"""Exercise Chromium startup failures using real synthetic child processes."""
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest import SkipTest
from unittest.mock import patch

from django.test import SimpleTestCase


class BrowserLauncherTests(SimpleTestCase):
    def test_missing_tooling_fails_ci_and_only_skips_local_development(self):
        from apps.core.test_review_admin_layout import ReviewAdminDesktopLayoutTests
        from apps.patients.test_closeout_layout import FinalCloseoutLayoutTests
        from apps.patients.test_phone_picker_layout import PatientPhonePickerLayoutTests
        from apps.patients.test_transient_layout import GuestConsultationLayoutTests

        cases = (
            (ReviewAdminDesktopLayoutTests, "test_long_review_text_and_moderation_controls_fit_desktop"),
            (FinalCloseoutLayoutTests, "test_notifications_reviews_and_folder_text_geometry"),
            (PatientPhonePickerLayoutTests, "test_portal_matches_login_computed_mobile_layout"),
            (GuestConsultationLayoutTests, "test_guest_states_all_requested_widths_in_arabic_and_english"),
        )
        for case, method in cases:
            for ci in (False, True):
                with self.subTest(case=case.__name__, ci=ci):
                    with patch.dict(os.environ, {"CI": str(ci).lower(), "GITHUB_ACTIONS": "false"}):
                        with patch("shutil.which", return_value=None), patch.object(Path, "is_file", return_value=False):
                            expected = AssertionError if ci else SkipTest
                            with self.assertRaises(expected):
                                getattr(case(method), method)()

    def test_startup_diagnostics_flags_and_cleanup(self):
        node = shutil.which("node")
        if not node:
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Node is required for browser launcher QA in CI")
            self.skipTest("Install Node for browser launcher QA")
        script = Path(__file__).parent / "js_tests" / "browser_launcher_test.js"
        with TemporaryDirectory(prefix="kbc-browser-launcher-") as directory:
            result = subprocess.run(
                [node, "--test", "--test-reporter=tap", str(script)],
                capture_output=True, text=True, encoding="utf-8", timeout=45,
                env={**os.environ, "KBC_LAUNCHER_TEST_DIR": directory},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
