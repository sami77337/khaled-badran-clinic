from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.html import escape

from apps.clinic.models import Doctor
from .models import DoctorPageContent
from .templatetags.branding import APPROVED_LOGO_PATH
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
        for query, label in (("", "الملف التعريفي للطبيب"), ("?lang=en", "Doctor Profile")):
            dashboard = self.client.get(reverse("dashboard_home") + query)
            self.assertContains(dashboard, label)
            self.assertContains(
                dashboard, reverse("admin:core_doctorpagecontent_changelist")
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
    def test_missing_asset_preserves_existing_identity_and_icon(self):
        with patch("apps.core.templatetags.branding.finders.find", return_value=None):
            for route in ("home", "login_en", "patient_portal_register"):
                response = self.client.get(reverse(route))
                self.assertNotContains(response, APPROVED_LOGO_PATH)
                self.assertContains(response, "img/icons/site-icon.svg")

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
                "patient_portal_register_en",
                "patient_portal_account_recovery",
            ):
                response = self.client.get(reverse(route))
                self.assertContains(response, f'src="/static/{APPROVED_LOGO_PATH}"')
                self.assertContains(
                    response, f'href="/static/{APPROVED_LOGO_PATH}" type="image/png"'
                )
                self.assertContains(response, "css/brand-closeout.css")
            self.client.force_login(staff)
            response = self.client.get(reverse("dashboard_home"))
            self.assertContains(
                response, f'src="/static/{APPROVED_LOGO_PATH}"', count=2
            )
            self.assertContains(response, "css/brand-closeout.css")
