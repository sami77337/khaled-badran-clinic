"""Real AR/EN Django pages rendered in installed headless Chromium."""
import json
import os
from datetime import timedelta
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.patients.models import TransientConsultation, TransientConsultationAudioReply, TransientConsultationChallenge


class GuestConsultationLayoutTests(TestCase):
    def test_guest_states_all_requested_widths_in_arabic_and_english(self):
        candidates = [os.environ.get("KBC_QA_BROWSER"), shutil.which("chromium"), shutil.which("google-chrome"),
                      "C:/Program Files/Google/Chrome/Application/chrome.exe",
                      "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"]
        browser = next((item for item in candidates if item and Path(item).is_file()), None)
        if not browser or not shutil.which("node"):
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Node and Chromium are required for guest layout QA in CI")
            self.skipTest("Install Chromium or set KBC_QA_BROWSER for guest layout QA")
        staff = get_user_model().objects.create_user(username="synthetic-guest-layout-staff", is_staff=True)
        pages = {}
        with TemporaryDirectory(prefix="kbc-guest-layout-") as directory:
            with override_settings(PRIVATE_MEDIA_ROOT=Path(directory) / "private", GUEST_CONSULTATION_OTP_SENDER=lambda *args: True):
                with patch("apps.patients.transient_services.generate_otp_code", return_value="123456"):
                    for language in ("ar", "en"):
                        cache.clear()
                        client = Client()
                        entry = reverse("guest_consultation_entry" + ("_en" if language == "en" else ""))
                        def capture(name, response):
                            self.assertIn(response.status_code, (200, 429))
                            pages[name + "-" + language] = response.content.decode()
                        capture("phone", client.get(entry))
                        capture("phone-error", client.post(entry, {"action": "send", "phone": "invalid"}))
                        self.assertEqual(client.post(entry, {"action": "send", "phone": "+12025550101"}).status_code, 302)
                        capture("otp", client.get(entry))
                        capture("otp-error", client.post(entry, {"action": "verify", "code": "000000"}))
                        TransientConsultationChallenge.objects.filter(verified_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
                        capture("expired", client.get(entry))
                        capture("rate-limit", client.post(entry, {"action": "resend"}))
                        cache.clear()
                        client.post(entry, {"action": "resend"})
                        client.post(entry, {"action": "verify", "code": "123456"})
                        capture("form", client.get(entry))
                        capture("attachment-error", client.post(entry, {"action": "submit", "question": "Synthetic",
                            "attachments": SimpleUploadedFile("synthetic.html", b"synthetic", content_type="text/html")}))
                        long_text = ("س" * 350 + " W" + "W" * 350 + " https://example.test/" + "x" * 300 + "\n") * 4
                        response = client.post(entry, {"action": "submit", "question": long_text, "display_name": "W" * 100,
                            "attachments": SimpleUploadedFile("W" * 235 + ".pdf", b"synthetic", content_type="application/pdf")})
                        self.assertEqual(response.status_code, 302)
                        detail = response.url
                        guest = TransientConsultation.objects.latest("id")
                        capture("success", client.get(detail))
                        capture("awaiting", client.get(detail))
                        guest.staff_reply = long_text
                        guest.status = "answered"
                        guest.save()
                        capture("answered", client.get(detail))
                        guest.staff_reply = ""
                        guest.save()
                        capture("empty-reply", client.get(detail))
                        audio = TransientConsultationAudioReply.objects.create(consultation=guest, created_by=staff,
                            file=SimpleUploadedFile("synthetic.webm", b"synthetic", content_type="audio/webm"))
                        capture("voice-only", client.get(detail))
                        audio.delete()
                        guest.status = "closed"
                        guest.save()
                        capture("closed", client.get(detail))
                        fresh = Client()
                        capture("reverification", fresh.get(detail))
                        cache.clear()
                        fresh.post(detail, {"action": "send"})
                        capture("reverification-otp", fresh.get(detail))
                        cache.clear()
                        with override_settings(GUEST_CONSULTATION_OTP_SENDER=""):
                            capture("otp-unavailable", Client().post(entry, {"action": "send", "phone": "+12025550102"}))
                        staff_client = Client()
                        staff_client.force_login(staff)
                        staff_url = reverse("dashboard_guest_consultation_detail", kwargs={"public_id": guest.public_id}) + "?lang=" + language
                        capture("staff-unavailable", staff_client.get(staff_url))
                        with override_settings(WHATSAPP_CONSULTATION_NOTIFICATION_SENDER=lambda *args: True, WHATSAPP_WEBSITE_ORIGIN="https://clinic.example.test"):
                            capture("staff-reply", staff_client.get(staff_url))
                fixture = Path(directory) / "pages.json"
                fixture.write_text(json.dumps(pages), encoding="utf-8")
                result = subprocess.run(
                    ["node", str(settings.BASE_DIR / "apps/patients/js_tests/transient_layout_test.js"),
                     browser, str(fixture), str(settings.BASE_DIR), os.environ.get("KBC_GUEST_QA_DIR", "")],
                    capture_output=True, text=True, encoding="utf-8", timeout=240,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                print(result.stdout.strip())
