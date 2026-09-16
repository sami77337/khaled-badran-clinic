import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from apps.clinic.models import Doctor
from apps.core.models import (
    AuditLog,
    DoctorPageContent,
    DoctorPageSection,
    PublicSiteContent,
)
from apps.core.public_copy import HOME_VISIBILITY, copy_definitions
from apps.core.views import DOCTOR_PUBLIC_PROFILE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="synthetic-owner",
            password="Synthetic-original-482!",
            is_staff=True,
        )
        self.url = reverse("dashboard_password_change")
        self.data = {
            "old_password": "Synthetic-original-482!",
            "new_password1": "Synthetic-replacement-725!",
            "new_password2": "Synthetic-replacement-725!",
        }

    def test_anonymous_and_nonstaff_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.user.is_staff = False
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.data).status_code, 403)

    def test_changes_only_self_hashes_password_and_retains_session(self):
        other = get_user_model().objects.create_user(
            username="synthetic-other", password="Other-synthetic-382!", is_staff=True
        )
        self.client.force_login(self.user)
        response = self.client.post(
            self.url, {**self.data, "user_id": other.pk}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(self.user.check_password(self.data["new_password1"]))
        self.assertNotEqual(self.user.password, self.data["new_password1"])
        self.assertTrue(other.check_password("Other-synthetic-382!"))
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
        self.assertEqual(self.client.get(reverse("dashboard_home")).status_code, 200)

    def test_bad_current_password_and_confirmation_rejected(self):
        self.client.force_login(self.user)
        for field in ("old_password", "new_password2"):
            response = self.client.post(
                self.url, {**self.data, field: "Wrong-synthetic-value"}
            )
            self.assertTrue(response.context["form"].errors)
            self.user.refresh_from_db()
            self.assertTrue(self.user.check_password(self.data["old_password"]))

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {
                "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                "OPTIONS": {"min_length": 30},
            }
        ]
    )
    def test_configured_django_validators_remain_active(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.data)
        self.assertIn("new_password2", response.context["form"].errors)

    def test_csrf_sensitive_parameters_methods_and_cache_boundary(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, self.data).status_code, 403)
        response = client.get(self.url)
        for flag in ("private", "no-store", "no-cache"):
            self.assertIn(flag, response["Cache-Control"])
        self.assertEqual(client.put(self.url).status_code, 403)
        client.post(
            self.url,
            {**self.data, "csrfmiddlewaretoken": client.cookies["csrftoken"].value},
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.data["new_password1"]))
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.data)
        self.assertEqual(
            set(response.wsgi_request.sensitive_post_parameters), set(self.data)
        )
        self.assertNotContains(response, self.data["new_password1"])

    def test_arabic_and_english(self):
        self.client.force_login(self.user)
        for query, label, direction in (
            ("", "كلمة المرور الحالية", "rtl"),
            ("?lang=en", "Current password", "ltr"),
        ):
            response = self.client.get(self.url + query)
            self.assertContains(response, label)
            self.assertContains(response, f'dir="{direction}"')
            self.assertContains(response, 'autocomplete="current-password"')
            self.assertContains(response, 'autocomplete="new-password"')


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ContentManagerTests(TestCase):
    def setUp(self):
        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب تجريبي", full_name_en="Synthetic Doctor"
        )
        self.owner = get_user_model().objects.create_superuser(
            username="synthetic-editor"
        )
        self.client.force_login(self.owner)

    def section_url(self, key):
        return reverse("dashboard_doctor_section", args=[key])

    def section_data(self, **changes):
        return {
            "title_ar": "قسم تجريبي",
            "title_en": "Synthetic section",
            "content_ar": "نص تجريبي\nعنصر ثان",
            "content_en": "Synthetic text\nSecond item",
            "presentation": "LIST",
            "display_order": 90,
            "is_visible": True,
            **changes,
        }

    def test_all_manager_routes_require_staff_and_permissions(self):
        urls = [
            reverse("dashboard_content"),
            reverse("dashboard_doctor_bio"),
            reverse("dashboard_doctor_section_new"),
            self.section_url("awards"),
            reverse("dashboard_public_copy", args=["home"]),
        ]
        for staff_flag in (False, True):
            user = get_user_model().objects.create_user(
                username=f"synthetic-unauthorized-{staff_flag}", is_staff=staff_flag
            )
            self.client.force_login(user)
            for url in urls:
                for method in (self.client.get, self.client.post):
                    expected = (
                        405
                        if staff_flag
                        and method == self.client.post
                        and url == reverse("dashboard_content")
                        else 403
                    )
                    self.assertEqual(method(url).status_code, expected, url)
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_model_permissions_apply_to_each_surface_and_creation(self):
        staff = get_user_model().objects.create_user(
            username="synthetic-limited-editor", is_staff=True
        )
        staff.user_permissions.add(
            Permission.objects.get(codename="view_doctorpagecontent")
        )
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("dashboard_content")).status_code, 200)
        self.assertEqual(
            self.client.post(reverse("dashboard_doctor_bio"), {}).status_code, 403
        )
        staff.user_permissions.add(
            Permission.objects.get(codename="add_doctorpagecontent")
        )
        self.assertEqual(
            self.client.post(
                reverse("dashboard_doctor_bio"),
                {"professional_bio_en": "Synthetic biography"},
            ).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(reverse("dashboard_doctor_bio"), {}).status_code, 403
        )
        staff.user_permissions.add(
            Permission.objects.get(codename="change_doctorpagecontent")
        )
        self.assertEqual(
            self.client.post(
                reverse("dashboard_doctor_bio"),
                {"professional_bio_en": "Updated synthetic biography"},
            ).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(
                self.section_url("awards"), self.section_data()
            ).status_code,
            403,
        )

    def test_no_rows_needed_for_defaults_and_get_never_creates_content(self):
        for language in ("ar", "en"):
            suffix = "_en" if language == "en" else ""
            response = self.client.get(reverse("doctor" + suffix))
            for key, values in DOCTOR_PUBLIC_PROFILE[language].items():
                if key == "memberships":
                    continue
                for value in values:
                    self.assertContains(response, escape(value))
            for page in ("home", "services", "contact"):
                self.assertEqual(
                    self.client.get(reverse(page + suffix)).status_code, 200
                )
        self.client.get(self.section_url("awards"))
        self.client.get(reverse("dashboard_doctor_bio"))
        self.assertFalse(DoctorPageContent.objects.exists())
        self.assertFalse(DoctorPageSection.objects.exists())
        self.assertFalse(PublicSiteContent.objects.exists())

    def test_existing_content_is_preserved_and_section_edits_reuse_legacy_fields(self):
        content = DoctorPageContent.objects.create(
            doctor=self.doctor,
            experience_en="Existing synthetic experience",
            awards_en="Existing synthetic award",
        )
        self.client.post(
            self.section_url("awards"),
            self.section_data(content_en="New synthetic award"),
        )
        content.refresh_from_db()
        self.assertEqual(content.experience_en, "Existing synthetic experience")
        self.assertEqual(content.awards_en, "New synthetic award")
        self.assertEqual(DoctorPageSection.objects.get(key="awards").content_en, "")
        self.assertContains(
            self.client.get(reverse("doctor_en")), "New synthetic award"
        )

    def test_hidden_awards_never_fall_back_and_can_be_restored(self):
        for visible in (False, True):
            response = self.client.post(
                self.section_url("awards"),
                self.section_data(content_ar="", content_en="", is_visible=visible),
            )
            self.assertEqual(response.status_code, 302)
            for route in ("doctor", "doctor_en"):
                html = self.client.get(reverse(route)).content.decode()
                self.assertEqual('data-doctor-section="awards"' in html, visible)
                if not visible:
                    for lang in ("ar", "en"):
                        self.assertNotIn(DOCTOR_PUBLIC_PROFILE[lang]["awards"][0], html)

    def test_editor_placeholders_match_public_content_after_clearing_overrides(self):
        self.doctor.bio_ar = "نبذة الطبيب الأصلية التجريبية"
        self.doctor.bio_en = "Original synthetic doctor biography"
        self.doctor.save()
        content = DoctorPageContent.objects.create(
            doctor=self.doctor,
            **{
                f"{field}_{lang}": f"Saved synthetic {field} {lang}"
                for lang in ("ar", "en")
                for field in (
                    "hero_summary", "credential_label", "professional_bio", "awards"
                )
            },
        )
        hints = {}
        for language in ("ar", "en"):
            bio_form = self.client.get(
                reverse("dashboard_doctor_bio") + f"?lang={language}"
            ).context["form"]
            hints[language] = []
            for field in ("hero_summary", "credential_label", "professional_bio"):
                name = f"{field}_{language}"
                self.assertEqual(bio_form[name].value(), getattr(content, name))
                hint = bio_form.fields[name].widget.attrs["placeholder"]
                self.assertNotEqual(hint, getattr(content, name))
                hints[language].append(hint)
            self.assertEqual(hints[language][-1], getattr(self.doctor, f"bio_{language}"))
            section_form = self.client.get(
                self.section_url("awards") + f"?lang={language}"
            ).context["form"]
            self.assertEqual(
                section_form[f"content_{language}"].value(),
                getattr(content, f"awards_{language}"),
            )
            hints[language].extend(
                section_form.fields[f"content_{language}"].widget.attrs[
                    "placeholder"
                ].splitlines()
            )
            hints[language].append(
                section_form.fields[f"title_{language}"].widget.attrs["placeholder"]
            )
        self.assertEqual(
            self.client.post(reverse("dashboard_doctor_bio"), {}).status_code, 302
        )
        self.assertEqual(
            self.client.post(
                self.section_url("awards"),
                self.section_data(title_ar="", title_en="", content_ar="", content_en=""),
            ).status_code,
            302,
        )
        for language, values in hints.items():
            response = self.client.get(reverse("doctor_en" if language == "en" else "doctor"))
            for hint in values:
                self.assertContains(response, escape(hint))
            self.assertNotContains(response, "Saved synthetic")

    def test_order_works_across_professional_clinical_and_custom_sections(self):
        self.client.post(
            self.section_url("conditions"), self.section_data(display_order=1)
        )
        self.client.post(self.section_url("awards"), self.section_data(display_order=2))
        self.client.post(
            reverse("dashboard_doctor_section_new"), self.section_data(display_order=3)
        )
        response = self.client.get(reverse("doctor_en"))
        html = response.content.decode()
        positions = [
            html.index(f'data-doctor-section="{key}"')
            for key in (
                "conditions",
                "awards",
                f"custom-{DoctorPageSection.objects.get(key='').pk}",
                "experience",
            )
        ]
        self.assertEqual(positions, sorted(positions))

    def test_custom_create_archive_restore(self):
        url = reverse("dashboard_doctor_section_new")
        self.assertEqual(self.client.post(url, self.section_data()).status_code, 302)
        section = DoctorPageSection.objects.get(key="")
        url = self.section_url(f"custom-{section.pk}")
        for archived in (True, False):
            self.assertEqual(
                self.client.post(
                    url, self.section_data(is_archived=archived)
                ).status_code,
                302,
            )
            html = self.client.get(reverse("doctor_en")).content.decode()
            self.assertEqual("Synthetic section" in html, not archived)

    def test_incomplete_custom_translation_can_be_draft_but_not_published(self):
        url = reverse("dashboard_doctor_section_new")
        response = self.client.post(url, self.section_data(content_en=""))
        self.assertIn("content_en", response.context["form"].errors)
        self.assertEqual(
            self.client.post(
                url, self.section_data(content_en="", is_visible=False)
            ).status_code,
            302,
        )
        section = DoctorPageSection.objects.get()
        section.is_visible = True
        section.save()
        self.assertNotContains(self.client.get(reverse("doctor")), "قسم تجريبي")

    def test_all_modes_localize_and_escape_even_rows_written_outside_forms(self):
        for mode, marker in (
            ("TEXT", 'class="public-section-text"'),
            ("LIST", "<ul>"),
            ("CHIPS", 'class="specialty-chip-list"'),
            ("CARDS", 'class="doctor-condition-grid"'),
        ):
            with self.subTest(mode=mode):
                section = DoctorPageSection.objects.create(
                    doctor=self.doctor,
                    **self.section_data(
                        presentation=mode,
                        content_ar="<script>تجريبي</script>",
                        content_en="<img src=x onerror=alert(1)>",
                    ),
                )
                for route, value in (
                    ("doctor", section.content_ar),
                    ("doctor_en", section.content_en),
                ):
                    response = self.client.get(reverse(route))
                    self.assertContains(response, marker)
                    self.assertContains(response, escape(value))
                    self.assertNotContains(response, value)
                section.delete()

    def test_editor_rejects_html_links_and_unapproved_display_types(self):
        url = reverse("dashboard_doctor_section_new")
        for text in (
            "<script>alert(1)</script>",
            "https://example.test",
            "[label](anything)",
        ):
            response = self.client.post(url, self.section_data(content_en=text))
            self.assertIn("content_en", response.context["form"].errors)
        response = self.client.post(url, self.section_data(presentation="HTML"))
        self.assertIn("presentation", response.context["form"].errors)
        self.assertFalse(DoctorPageSection.objects.exists())

    def test_public_copy_allowlist_bilingual_fallback_visibility_and_escaping(self):
        url = reverse("dashboard_public_copy", args=["home"])
        data = {key.replace(".", "_"): True for key in HOME_VISIBILITY}
        data.update(
            home_contact_title_ar="عنوان تجريبي",
            home_contact_title_en="Synthetic heading",
            privacy_policy_ar="Unapproved change",
        )
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertContains(self.client.get(reverse("home")), "عنوان تجريبي")
        self.assertContains(self.client.get(reverse("home_en")), "Synthetic heading")
        self.assertFalse(
            PublicSiteContent.objects.filter(key__contains="privacy").exists()
        )
        self.assertFalse(any("privacy" in key for key in copy_definitions()))
        self.assertEqual(
            self.client.get(
                reverse("dashboard_public_copy", args=["privacy"])
            ).status_code,
            404,
        )
        data.update(home_section_doctor=False, home_contact_title_en="")
        self.client.post(url, data)
        self.assertNotContains(
            self.client.get(reverse("home")), 'class="section home-doctor"'
        )
        self.assertContains(self.client.get(reverse("home_en")), "We’re here to help")
        PublicSiteContent.objects.filter(key="home.contact_title").update(
            text_en="<script>synthetic</script>"
        )
        response = self.client.get(reverse("home_en"))
        self.assertContains(response, escape("<script>synthetic</script>"))
        self.assertNotContains(response, "<script>synthetic</script>")

    def test_services_contact_and_doctor_headings_editable(self):
        for page, key, route in (
            ("services", "services.headline", "services_en"),
            ("contact", "contact.subtitle", "contact_en"),
            ("doctor", "doctor.bio_title", "doctor_en"),
        ):
            response = self.client.post(
                reverse("dashboard_public_copy", args=[page]),
                {key.replace(".", "_") + "_en": "Synthetic presentation copy"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertContains(
                self.client.get(reverse(route)), "Synthetic presentation copy"
            )

    def test_post_csrf_no_cache_audit_and_no_doctor_retargeting(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        for url in (
            reverse("dashboard_doctor_bio"),
            self.section_url("awards"),
            reverse("dashboard_doctor_section_new"),
            reverse("dashboard_public_copy", args=["home"]),
        ):
            self.assertEqual(client.post(url, self.section_data()).status_code, 403)
            self.assertIn("no-store", client.get(url)["Cache-Control"])
        other = Doctor.objects.create(
            full_name_ar="طبيب آخر تجريبي",
            full_name_en="ZZ Synthetic Other",
            is_active=False,
        )
        self.client.post(self.section_url("awards"), self.section_data(doctor=other.pk))
        self.assertEqual(DoctorPageSection.objects.get().doctor, self.doctor)
        self.assertFalse(DoctorPageContent.objects.filter(doctor=other).exists())
        self.assertTrue(
            AuditLog.objects.filter(metadata__event="public_content_saved").exists()
        )

    def test_manager_ar_en_and_four_modes(self):
        for lang, title, direction in (
            ("ar", "محتوى الموقع", "rtl"),
            ("en", "Website Content", "ltr"),
        ):
            response = self.client.get(reverse("dashboard_content") + f"?lang={lang}")
            self.assertContains(response, title)
            self.assertContains(response, f'dir="{direction}"')
            response = self.client.get(
                reverse("dashboard_doctor_section_new") + f"?lang={lang}"
            )
            for mode in ("TEXT", "LIST", "CHIPS", "CARDS"):
                self.assertContains(response, f'value="{mode}"')


class InstallAppTests(TestCase):
    def test_manifest_approved_icons_and_worker_has_no_private_cache(self):
        manifest = json.loads(
            (settings.BASE_DIR / "static/site.webmanifest").read_text()
        )
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(
            [Path(icon["src"]).name for icon in manifest["icons"]],
            ["KB_APPROVED_PWA_192.png", "KB_APPROVED_PWA_512.png"],
        )
        worker = (settings.BASE_DIR / "static/sw.js").read_text(encoding="utf-8")
        for fragment in (
            'addEventListener("fetch"',
            "caches.",
            "indexedDB",
            "localStorage",
        ):
            self.assertNotIn(fragment, worker)
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        response.close()

    def test_public_dashboard_and_ios_copy_in_ar_en(self):
        staff = get_user_model().objects.create_user(
            username="synthetic-install-staff", is_staff=True
        )
        self.client.force_login(staff)
        for url, label, instructions in (
            ("/", "تثبيت التطبيق", "اضغط زر المشاركة"),
            ("/en/", "Install App", "Tap Share"),
            ("/dashboard/", "تثبيت التطبيق", "اضغط زر المشاركة"),
            ("/dashboard/?lang=en", "Install App", "Tap Share"),
        ):
            response = self.client.get(url)
            self.assertContains(response, label)
            self.assertContains(response, instructions)
            self.assertContains(response, "data-install-app")
            self.assertContains(response, 'method="dialog"')
