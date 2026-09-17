import hashlib
import json
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escape

from apps.clinic.models import Doctor
from .models import DoctorPageContent
from .templatetags.branding import (
    APPROVED_APPLE_TOUCH_ICON_PATH,
    APPROVED_FAVICON_PATH,
    APPROVED_LOGO_PATH,
)
from .views import DOCTOR_DEFAULT, DOCTOR_PUBLIC_PROFILE


class DoctorContentTests(TestCase):
    def setUp(self):
        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب تجريبي", full_name_en="Synthetic Doctor"
        )

    def test_absent_and_blank_content_keep_approved_copy_and_existing_doctor_bio(self):
        for content_exists in (False, True):
            if content_exists:
                DoctorPageContent.objects.create(
                    doctor=self.doctor, hero_summary_ar="  "
                )
            for language in ("ar", "en"):
                response = self.client.get(
                    reverse("doctor" + ("_en" if language == "en" else ""))
                )
                self.assertContains(
                    response, DOCTOR_DEFAULT[f"hero_summary_{language}"]
                )
                for text in DOCTOR_PUBLIC_PROFILE[language]["experience"]:
                    self.assertContains(response, escape(text))
                self.assertContains(response, 'class="doctor-details-grid"')
                self.assertContains(response, 'class="professional-profile-card"')
                self.assertContains(response, 'class="doctor-condition-grid"')
        self.doctor.bio_en = "Existing synthetic professional biography."
        self.doctor.save()
        self.assertContains(self.client.get(reverse("doctor_en")), self.doctor.bio_en)

    def test_no_active_doctor_keeps_fallback(self):
        self.doctor.delete()
        self.assertContains(
            self.client.get(reverse("doctor_en")), DOCTOR_DEFAULT["bio_en"]
        )

    def test_saved_text_and_all_lists_are_localized_and_escaped(self):
        data = {}
        lists = (
            "experience",
            "education",
            "boards",
            "awards",
            "languages",
            "specialties",
            "conditions",
        )
        for language in ("ar", "en"):
            for field in (
                "hero_summary",
                "professional_bio",
                "credential_label",
                *lists,
            ):
                data[f"{field}_{language}"] = f"<{field}-{language}>" + (
                    "\nSecond synthetic item" if field in lists else ""
                )
            data[f"memberships_{language}"] = (
                f"Synthetic membership {language} | SYN-{language}\nSYN2-{language}"
            )
        DoctorPageContent.objects.create(doctor=self.doctor, **data)
        for language in ("ar", "en"):
            response = self.client.get(
                reverse("doctor" + ("_en" if language == "en" else ""))
            )
            for field in (
                "hero_summary",
                "professional_bio",
                "credential_label",
                *lists,
            ):
                self.assertContains(response, escape(f"<{field}-{language}>"))
                self.assertNotContains(response, f"<{field}-{language}>")
            self.assertContains(response, f"SYN-{language}</bdi>")
            self.assertContains(response, f"SYN2-{language}</bdi>")

    def test_partial_translation_and_inactive_doctor_do_not_replace_other_content(self):
        DoctorPageContent.objects.create(
            doctor=self.doctor, education_en="Saved synthetic education"
        )
        self.assertContains(
            self.client.get(reverse("doctor_en")), "Saved synthetic education"
        )
        self.assertNotContains(
            self.client.get(reverse("doctor")), "Saved synthetic education"
        )
        self.doctor.is_active = False
        self.doctor.save()
        self.assertNotContains(
            self.client.get(reverse("doctor_en")), "Saved synthetic education"
        )

    def test_authorized_staff_can_create_and_edit_using_existing_admin(self):
        staff = get_user_model().objects.create_user(
            username="synthetic-content-editor", is_staff=True
        )
        staff.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="core",
                codename__in=[
                    "view_doctorpagecontent",
                    "add_doctorpagecontent",
                    "change_doctorpagecontent",
                ],
            )
        )
        self.client.force_login(staff)
        for query, label in (("", "محتوى الموقع"), ("?lang=en", "Website Content")):
            dashboard = self.client.get(reverse("dashboard_home") + query)
            self.assertContains(dashboard, label)
            self.assertContains(
                dashboard, reverse("dashboard_content")
            )
        url = reverse("admin:core_doctorpagecontent_add")
        data = {
            "doctor": self.doctor.pk,
            "experience_ar": "خبرة تجريبية",
            "experience_en": "Synthetic experience",
            "_save": "Save",
        }
        self.assertEqual(self.client.post(url, data).status_code, 302)
        content = DoctorPageContent.objects.get(doctor=self.doctor)
        url = reverse("admin:core_doctorpagecontent_change", args=[content.pk])
        data["credential_label_en"] = "Synthetic credential"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        content.refresh_from_db()
        self.assertEqual(content.credential_label_en, "Synthetic credential")
        self.assertContains(
            self.client.get(reverse("doctor_en")), "Synthetic credential"
        )

    def test_content_admin_requires_permissions_and_csrf(self):
        content = DoctorPageContent.objects.create(doctor=self.doctor)
        url = reverse("admin:core_doctorpagecontent_change", args=[content.pk])
        for staff_flag, expected in ((False, 302), (True, 403)):
            user = get_user_model().objects.create_user(
                username=f"synthetic-content-{staff_flag}", is_staff=staff_flag
            )
            self.client.force_login(user)
            self.assertEqual(
                self.client.post(url, {"doctor": self.doctor.pk}).status_code, expected
            )
            if staff_flag:
                self.assertNotContains(
                    self.client.get(reverse("dashboard_home")),
                    reverse("admin:core_doctorpagecontent_changelist"),
                )
        user = get_user_model().objects.create_superuser(
            username="synthetic-content-owner"
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(client.post(url, {"doctor": self.doctor.pk}).status_code, 403)


class BrandingContractTests(TestCase):
    def assert_approved_site_icons(self, response):
        self.assertContains(
            response,
            '<link rel="icon" href="/static/img/brand/KB_APPROVED_256.png" type="image/png">',
            count=1,
        )
        self.assertContains(
            response,
            '<link rel="apple-touch-icon" href="/static/img/brand/KB_APPROVED_APPLE_TOUCH_180.png" sizes="180x180">',
            count=1,
        )
        self.assertNotContains(response, "img/icons/site-icon.svg")
        self.assertNotContains(response, "kb-approved.png")

    def test_missing_asset_preserves_existing_identity_and_icon(self):
        with patch("apps.core.templatetags.branding.finders.find", return_value=None):
            for route in ("home", "login_en", "patient_portal_register"):
                response = self.client.get(reverse(route))
                self.assertNotContains(response, APPROVED_LOGO_PATH)
                self.assertContains(response, "img/icons/site-icon.svg")
                self.assertNotContains(response, 'rel="apple-touch-icon"')
                self.assertNotContains(response, "kb-approved.png")

    def test_exact_asset_is_used_on_public_auth_dashboard_and_site_icon(self):
        staff = get_user_model().objects.create_user(
            username="synthetic-brand-staff", is_staff=True
        )
        with patch(
            "apps.core.templatetags.branding.finders.find",
            return_value="synthetic-approved-file",
        ):
            for route in (
                "home",
                "home_en",
                "login",
                "login_en",
                "patient_portal_register",
                "patient_portal_register_en",
                "patient_portal_account_recovery",
                "patient_portal_account_recovery_en",
            ):
                response = self.client.get(reverse(route))
                self.assertContains(response, 'src="/static/img/brand/KB_APPROVED_WEB_512.png"')
                self.assert_approved_site_icons(response)
                self.assertContains(response, "css/brand-closeout.css")
            self.client.force_login(staff)
            response = self.client.get(reverse("dashboard_home"))
            self.assertContains(
                response, 'src="/static/img/brand/KB_APPROVED_WEB_512.png"', count=2
            )
            self.assertContains(response, "css/brand-closeout.css")
            self.assert_approved_site_icons(response)

    def test_each_site_icon_checks_its_own_asset_availability(self):
        for missing_path in (
            APPROVED_LOGO_PATH,
            APPROVED_FAVICON_PATH,
            APPROVED_APPLE_TOUCH_ICON_PATH,
        ):
            with self.subTest(missing_path=missing_path), patch(
                "apps.core.templatetags.branding.finders.find",
                side_effect=lambda path: None if path == missing_path else path,
            ):
                html = render_to_string("partials/site_icon.html")
                self.assertEqual(
                    "img/icons/site-icon.svg" in html,
                    missing_path == APPROVED_FAVICON_PATH,
                )
                self.assertEqual(
                    APPROVED_FAVICON_PATH in html,
                    missing_path != APPROVED_FAVICON_PATH,
                )
                self.assertEqual(
                    APPROVED_APPLE_TOUCH_ICON_PATH in html,
                    missing_path != APPROVED_APPLE_TOUCH_ICON_PATH,
                )
                self.assertNotIn(APPROVED_LOGO_PATH, html)
                self.assertNotIn("kb-approved.png", html)

    def test_manifest_uses_only_the_approved_192_and_512_png_icons(self):
        manifest = json.loads(
            (settings.BASE_DIR / "static/site.webmanifest").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["icons"], [
            {
                "src": "/static/img/brand/KB_APPROVED_PWA_192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/img/brand/KB_APPROVED_PWA_512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
        ])

    def test_brand_assets_match_the_exact_owner_approved_bytes(self):
        approved_hashes = {
            "KB_APPROVED_WEB_512.png": "47b20ec7aa3691ae5770451c8be33ab6ef37dbadce4e032ee22c5c5a341924c1",
            "KB_APPROVED_256.png": "6ad494ad5add4bc3598ad9d4ba9dd195776bbb761d1b357a4c859306d166d568",
            "KB_APPROVED_APPLE_TOUCH_180.png": "468f56233e0501bad6f4fa23fc02bc9e3d05fa4b2967632d35ade848f7e62acb",
            "KB_APPROVED_PWA_192.png": "d5f21e92c2268e3e9131568054535257aa094eb5aeaac87ff2e386299b3a76ea",
            "KB_APPROVED_PWA_512.png": "a0563c0a1fb0a6c90c9258f2d6627b2804bd0d28f1713010a76ce21bce1cee71",
        }
        for filename, expected_hash in approved_hashes.items():
            with self.subTest(filename=filename):
                path = settings.BASE_DIR / "static/img/brand" / filename
                self.assertTrue(path.is_file(), f"Missing owner-approved asset: {filename}")
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
