"""Desktop rendering of long patient-authored text in review moderation."""
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

from .models import PublicReview


class ReviewAdminDesktopLayoutTests(TestCase):
    def test_long_review_text_and_moderation_controls_fit_desktop(self):
        candidates = (
            os.environ.get("KBC_QA_BROWSER"), shutil.which("chromium"), shutil.which("google-chrome"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        )
        browser = next((item for item in candidates if item and Path(item).is_file()), None)
        if not browser or not shutil.which("node"):
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Node and Chromium are required for desktop layout QA in CI")
            self.skipTest("Install Node and Chromium or set KBC_QA_BROWSER for desktop layout QA")
        moderator = get_user_model().objects.create_superuser(username="synthetic-desktop-moderator")
        self.client.force_login(moderator)
        pages = {}
        for language in ("ar", "en"):
            review = PublicReview.objects.create(
                reviewer_name=("س" if language == "ar" else "W") * 160,
                body="تقييم عربي تجريبي طويل. " * 30 + "\nhttps://example.test/" + "x" * 500,
                rating=4, language=language, source=PublicReview.Source.PATIENT_PORTAL,
            )
            self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
            routes = {
                "list": reverse("admin:core_publicreview_changelist"),
                "detail": reverse("admin:core_publicreview_change", args=[review.pk]),
                "delete": reverse("admin:core_publicreview_delete", args=[review.pk]),
            }
            for surface, url in routes.items():
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                pages[f"{surface}-{language}"] = response.content.decode()
            form = self.client.get(routes["detail"]).context["adminform"].form
            review.body += " Updated synthetic revision."
            review.save()
            stale = self.client.post(routes["detail"], {
                "review_version": form["review_version"].value(), "is_approved_for_publication": "on",
                "is_active": "on", "display_order": 0, "_save": "Save",
            })
            self.assertContains(stale, "This review changed after you opened it.")
            pages[f"stale-{language}"] = stale.content.decode()

        assets = {}
        for html in pages.values():
            for url in re.findall(r'(?:href|src)="(/static/[^"?]+)', html):
                resolved = finders.find(url.removeprefix("/static/"))
                if resolved:
                    assets[url] = str(Path(resolved).resolve())
        with TemporaryDirectory(prefix="kbc-review-desktop-") as directory:
            fixture = Path(directory) / "pages.json"
            fixture.write_text(json.dumps({"pages": pages, "assets": assets}), encoding="utf-8")
            result = subprocess.run(
                ["node", str(settings.BASE_DIR / "apps/core/js_tests/review_admin_desktop_layout_test.js"),
                 browser, str(fixture)],
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
