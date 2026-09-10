import subprocess

from django.conf import settings
from django.test import SimpleTestCase


class ConsultationRecorderRuntimeTests(SimpleTestCase):
    def test_microphone_lifecycle_and_submission(self):
        result = subprocess.run(
            ["node", str(settings.BASE_DIR / "apps/patients/js_tests/consultation_recorder_runtime_test.js"),
             str(settings.BASE_DIR / "static/js/consultation-recorder.js")],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())
