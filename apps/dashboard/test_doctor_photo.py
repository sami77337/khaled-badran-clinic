import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.clinic.models import Doctor
from apps.core.models import DoctorPageContent


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DoctorPhotoContentManagerTests(TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.override = override_settings(PRIVATE_MEDIA_ROOT=Path(self.tempdir.name))
        self.override.enable()
        self.addCleanup(self.override.disable)

        self.doctor = Doctor.objects.create(
            full_name_ar="طبيب تجريبي",
            full_name_en="Synthetic Doctor",
            title_ar="د.",
            title_en="Dr.",
            is_active=True,
        )
        self.content = DoctorPageContent.objects.create(doctor=self.doctor)
        self.user = get_user_model().objects.create_user(
            username="synthetic-content-owner",
            password="Synthetic-content-482!",
            is_staff=True,
        )
        self.user.user_permissions.add(
            Permission.objects.get(codename="change_doctorpagecontent")
        )
        self.client.force_login(self.user)
        self.edit_url = reverse("dashboard_doctor_bio")
        self.photo_url = reverse("dashboard_doctor_public_photo")

    @staticmethod
    def png_upload(name="doctor.png"):
        return SimpleUploadedFile(
            name,
            b"\x89PNG\r\n\x1a\n" + b"synthetic-public-photo",
            content_type="image/png",
        )

    def test_editor_is_multipart_and_shows_current_photo_preview(self):
        response = self.client.get(self.edit_url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, "Replace doctor photo")
        self.assertContains(response, "owner-content-closeout.css")
        self.assertContains(response, "/static/img/doctor/dr-khaled-badran.png")

    def test_valid_upload_updates_home_doctor_page_and_public_route(self):
        response = self.client.post(self.edit_url, {"profile_photo": self.png_upload()})
        self.assertEqual(response.status_code, 302)

        self.content.refresh_from_db()
        self.assertTrue(self.content.profile_photo.name.startswith(f"doctor/{self.doctor.pk}/"))
        self.assertEqual(self.content.profile_photo_content_type, "image/png")

        public = self.client.get(self.photo_url)
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public["Content-Type"], "image/png")
        self.assertEqual(public["X-Content-Type-Options"], "nosniff")
        self.assertTrue(b"synthetic-public-photo" in b"".join(public.streaming_content))

        for route in ("home", "home_en", "doctor", "doctor_en"):
            page = self.client.get(reverse(route))
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, self.photo_url)

    def test_non_image_upload_is_rejected_without_replacing_photo(self):
        invalid = SimpleUploadedFile(
            "doctor.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            content_type="image/svg+xml",
        )
        response = self.client.post(self.edit_url, {"profile_photo": invalid})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("profile_photo"))
        self.content.refresh_from_db()
        self.assertFalse(self.content.profile_photo)
        self.assertEqual(self.client.get(self.photo_url).status_code, 404)

    def test_restore_default_clears_custom_photo_and_public_pages_fall_back(self):
        self.client.post(self.edit_url, {"profile_photo": self.png_upload()})
        self.content.refresh_from_db()
        old_name = self.content.profile_photo.name
        old_storage = self.content.profile_photo.storage
        self.assertTrue(old_storage.exists(old_name))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, {"remove_profile_photo": "on"})
        self.assertEqual(response.status_code, 302)
        self.content.refresh_from_db()
        self.assertFalse(self.content.profile_photo)
        self.assertEqual(self.content.profile_photo_content_type, "")
        self.assertFalse(old_storage.exists(old_name))
        self.assertEqual(self.client.get(self.photo_url).status_code, 404)

        for route in ("home", "doctor"):
            page = self.client.get(reverse(route))
            self.assertContains(page, "/static/img/doctor/dr-khaled-badran.png")

    def test_public_photo_route_never_exposes_unrelated_media_path(self):
        unrelated = Path(self.tempdir.name) / "unrelated-private.txt"
        unrelated.write_text("private", encoding="utf-8")
        self.assertEqual(self.client.get(self.photo_url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("home")), "unrelated-private.txt")
