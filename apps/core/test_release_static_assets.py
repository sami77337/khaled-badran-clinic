"""Regression tests for release-aware public static assets; synthetic-only."""

import os
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.templatetags.static import static
from django.test import TestCase, override_settings
from django.urls import reverse


RELEASE_A = "a" * 40
RELEASE_B = "b" * 40


class ReleaseVersionedStaticAssetsTests(TestCase):
    @override_settings(PRODUCTION=True)
    def test_css_javascript_and_images_change_urls_per_release(self):
        for path in (
            "css/site.css",
            "css/public.css",
            "css/public-closeout.css",
            "js/site.js",
            "img/clinic/clinic-interior-1.png",
            "img/brand/KB_APPROVED_PWA_192.png",
        ):
            with self.subTest(path=path):
                with patch.dict(os.environ, {"RENDER_GIT_COMMIT": RELEASE_A}):
                    first = static(path)
                with patch.dict(os.environ, {"RENDER_GIT_COMMIT": RELEASE_B}):
                    second = static(path)
                self.assertNotEqual(first, second)
                self.assertEqual(urlsplit(first).path, urlsplit(second).path)
                self.assertTrue(urlsplit(first).path.endswith("/" + path))
                self.assertEqual(parse_qs(urlsplit(first).query), {"v": ["a" * 12]})
                self.assertEqual(parse_qs(urlsplit(second).query), {"v": ["b" * 12]})

    @override_settings(PRODUCTION=True)
    def test_invalid_or_missing_commit_never_injects_public_query(self):
        for value in ("", "not-a-sha", "a" * 39, "a" * 40 + "&bad=1"):
            with self.subTest(revision=value):
                with patch.dict(os.environ, {"RENDER_GIT_COMMIT": value}):
                    self.assertNotIn("v=", static("css/site.css"))

    @override_settings(PRODUCTION=False)
    def test_nonproduction_static_urls_unchanged(self):
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": RELEASE_A}):
            self.assertNotIn("v=", static("css/site.css"))

    @override_settings(PRODUCTION=True)
    def test_public_home_ar_en_have_revalidated_html_and_release_assets(self):
        with patch.dict(os.environ, {"RENDER_GIT_COMMIT": RELEASE_A}):
            for name in ("home", "home_en"):
                with self.subTest(route=name):
                    response = self.client.get(reverse(name))
                    self.assertEqual(response.status_code, 200)
                    html = response.content.decode()
                    self.assertIn("css/site.css?v=" + "a" * 12, html)
                    self.assertIn("css/public-closeout.css?v=" + "a" * 12, html)
                    self.assertIn("js/site.js?v=" + "a" * 12, html)
                    self.assertIn("img/clinic/clinic-interior-1.png?v=" + "a" * 12, html)
                    self.assertIn("no-store", response["Cache-Control"])
