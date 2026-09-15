"""Render the dashboard review flow using isolated synthetic HTML fixtures."""
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

from apps.core.models import PublicReview


class DashboardPatientReviewLayoutTests(TestCase):
    def test_arabic_and_english_review_actions_fit_mobile_and_desktop(self):
        candidates = (
            os.environ.get("KBC_QA_BROWSER"), shutil.which("google-chrome"), shutil.which("chromium"),
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        )
        browser = next((item for item in candidates if item and Path(item).is_file()), None)
        if not browser or not shutil.which("node"):
            if os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true":
                self.fail("Node and Chromium are required for dashboard layout QA in CI")
            self.skipTest("Node and Chromium are required for dashboard layout QA")
        moderator = get_user_model().objects.create_superuser(username="synthetic-dashboard-layout-moderator")
        self.client.force_login(moderator)
        pages = {}
        for language in ("ar", "en"):
            url = reverse("dashboard_patient_reviews") + f"?lang={language}"
            pages[f"empty-{language}"] = self.client.get(url).content.decode()
            review = PublicReview.objects.create(
                source=PublicReview.Source.PATIENT_PORTAL, reviewer_name=("س" if language == "ar" else "W") * 160,
                body="تقييم تجريبي طويل. " * 30 + "\nhttps://example.test/" + "x" * 500,
                rating=4, language=language,
            )
            response = self.client.get(url)
            pages[f"hidden-{language}"] = response.content.decode()
            token = response.context["review_items"][0]["form"]["review_version"].value()
            review.is_approved_for_publication = True
            review.save()
            pages[f"visible-{language}"] = self.client.get(url).content.decode()
            delete_url = reverse("dashboard_patient_review_delete", args=[review.pk]) + f"?lang={language}"
            pages[f"delete-{language}"] = self.client.get(delete_url).content.decode()
            stale = self.client.post(reverse("dashboard_patient_review_visibility", args=[review.pk]) + f"?lang={language}", {
                "review_version": token, "moderation_action": "show",
            })
            self.assertEqual(stale.status_code, 400)
            pages[f"stale-{language}"] = stale.content.decode()
            review.delete()
        assets = {}
        for html in pages.values():
            for url in re.findall(r'(?:href|src)="(/static/[^"?]+)', html):
                resolved = finders.find(url.removeprefix("/static/"))
                if resolved:
                    assets[url] = str(Path(resolved).resolve())
        with TemporaryDirectory(prefix="kbc-dashboard-reviews-") as directory:
            fixture = Path(directory) / "pages.json"
            fixture.write_text(json.dumps({"pages": pages, "assets": assets}), encoding="utf-8")
            result = subprocess.run(
                ["node", str(settings.BASE_DIR / "apps/dashboard/js_tests/patient_review_layout_test.js"), browser, str(fixture)],
                capture_output=True, text=True, encoding="utf-8", timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
