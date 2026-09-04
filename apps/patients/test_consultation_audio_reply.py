from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.patients.models import (
    CONSULTATION_AUDIO_MAX_BYTES,
    Consultation,
    ConsultationAttachment,
    ConsultationAudioReply,
    Patient,
    validate_consultation_audio_upload,
)
from apps.patients.storage import consultation_audio_reply_storage
from apps.records.models import ClinicalNote, PublicCaseMedia, RecordMedia


class ConsultationAudioReplyTests(TestCase):
    password = "Audio-reply-pass-981!"

    @classmethod
    def setUpClass(cls):
        cls._private_media_directory = TemporaryDirectory()
        cls._private_media_override = override_settings(
            PRIVATE_MEDIA_ROOT=cls._private_media_directory.name
        )
        cls._private_media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._private_media_override.disable()
        cls._private_media_directory.cleanup()

    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username="audio-doctor",
            password=self.password,
            is_staff=True,
        )
        self.patient_user = user_model.objects.create_user(
            username="+962790300001",
            password=self.password,
        )
        self.other_user = user_model.objects.create_user(
            username="+962790300002",
            password=self.password,
        )
        self.patient = Patient.objects.create(
            user=self.patient_user,
            full_name="Audio Reply Patient",
            phone_raw=self.patient_user.username,
            phone_e164=self.patient_user.username,
        )
        self.other_patient = Patient.objects.create(
            user=self.other_user,
            full_name="Other Audio Patient",
            phone_raw=self.other_user.username,
            phone_e164=self.other_user.username,
        )

    def create_consultation(self, *, patient=None):
        return Consultation.objects.create(
            patient=patient or self.patient,
            question="Private voice consultation question",
        )

    def audio_upload(
        self,
        name="doctor-reply.webm",
        content_type="audio/webm",
        content=b"synthetic-browser-audio",
    ):
        return SimpleUploadedFile(name, content, content_type=content_type)

    def create_audio_reply(self, consultation, **upload_kwargs):
        upload = self.audio_upload(**upload_kwargs)
        return ConsultationAudioReply.objects.create(
            consultation=consultation,
            file=upload,
            created_by=self.staff,
            **validate_consultation_audio_upload(upload),
        )

    def staff_reply_url(self, consultation):
        return reverse(
            "dashboard_consultation_detail",
            kwargs={"public_id": consultation.public_id},
        )

    def test_server_accepts_only_allowed_matching_browser_audio_formats(self):
        allowed = (
            ("reply.webm", "audio/webm"),
            ("reply.webm", "audio/webm;codecs=opus"),
            ("reply.ogg", "audio/ogg"),
            ("reply.m4a", "audio/mp4"),
            ("reply.mp4", "audio/mp4"),
        )
        for name, content_type in allowed:
            with self.subTest(name=name, content_type=content_type):
                metadata = validate_consultation_audio_upload(
                    self.audio_upload(name=name, content_type=content_type)
                )
                self.assertIn(metadata["content_type"], {"audio/webm", "audio/ogg", "audio/mp4"})

        rejected = (
            ("reply.ogg", "audio/webm"),
            ("reply.webm", "audio/ogg"),
            ("reply.wav", "audio/wav"),
            ("reply.mp3", "audio/mpeg"),
            ("reply.exe", "application/octet-stream"),
        )
        for name, content_type in rejected:
            with self.subTest(name=name, content_type=content_type), self.assertRaises(
                ValidationError
            ):
                validate_consultation_audio_upload(
                    self.audio_upload(name=name, content_type=content_type)
                )

        with self.assertRaises(ValidationError):
            validate_consultation_audio_upload(
                self.audio_upload(content=b"x" * (CONSULTATION_AUDIO_MAX_BYTES + 1))
            )

    def test_text_only_audio_only_and_text_plus_audio_replies_are_saved(self):
        text_only = self.create_consultation()
        audio_only = self.create_consultation()
        text_and_audio = self.create_consultation()
        self.client.force_login(self.staff)

        text_response = self.client.post(
            self.staff_reply_url(text_only),
            {"staff_reply": "Written doctor reply", "status": Consultation.Status.ANSWERED},
        )
        audio_response = self.client.post(
            self.staff_reply_url(audio_only),
            {
                "staff_reply": "",
                "status": Consultation.Status.ANSWERED,
                "audio_reply": self.audio_upload(content_type="audio/webm;codecs=opus"),
            },
        )
        combined_response = self.client.post(
            self.staff_reply_url(text_and_audio),
            {
                "staff_reply": "Combined written reply",
                "status": Consultation.Status.ANSWERED,
                "audio_reply": self.audio_upload(name="combined.m4a", content_type="audio/mp4"),
            },
        )

        self.assertEqual(text_response.status_code, 302)
        self.assertEqual(audio_response.status_code, 302)
        self.assertEqual(combined_response.status_code, 302)
        text_only.refresh_from_db()
        audio_only.refresh_from_db()
        text_and_audio.refresh_from_db()
        self.assertEqual(text_only.staff_reply, "Written doctor reply")
        self.assertFalse(ConsultationAudioReply.objects.filter(consultation=text_only).exists())
        self.assertEqual(audio_only.staff_reply, "")
        self.assertEqual(audio_only.audio_reply.content_type, "audio/webm")
        self.assertEqual(text_and_audio.staff_reply, "Combined written reply")
        self.assertEqual(text_and_audio.audio_reply.content_type, "audio/mp4")
        for consultation in (text_only, audio_only, text_and_audio):
            self.assertIsNotNone(consultation.staff_handled_at)
            self.assertEqual(consultation.replied_by, self.staff)
            self.assertIsNotNone(consultation.replied_at)
        self.assertEqual(ConsultationAttachment.objects.count(), 0)
        self.assertEqual(RecordMedia.objects.count(), 0)
        self.assertEqual(ClinicalNote.objects.count(), 0)
        self.assertEqual(PublicCaseMedia.objects.count(), 0)

    def test_invalid_or_oversized_audio_is_rejected_without_changing_consultation(self):
        consultation = self.create_consultation()
        self.client.force_login(self.staff)

        mismatch = self.client.post(
            f"{self.staff_reply_url(consultation)}?lang=en",
            {
                "staff_reply": "",
                "status": Consultation.Status.ANSWERED,
                "audio_reply": self.audio_upload(name="mismatch.ogg", content_type="audio/webm"),
            },
        )
        oversized = self.client.post(
            f"{self.staff_reply_url(consultation)}?lang=en",
            {
                "staff_reply": "",
                "status": Consultation.Status.ANSWERED,
                "audio_reply": self.audio_upload(
                    content=b"x" * (CONSULTATION_AUDIO_MAX_BYTES + 1)
                ),
            },
        )

        self.assertEqual(mismatch.status_code, 200)
        self.assertEqual(oversized.status_code, 200)
        self.assertContains(oversized, "15 MiB")
        consultation.refresh_from_db()
        self.assertEqual(consultation.status, Consultation.Status.NEW)
        self.assertIsNone(consultation.staff_handled_at)
        self.assertFalse(ConsultationAudioReply.objects.exists())

    def test_patient_and_staff_playback_is_uuid_protected_and_owner_scoped(self):
        consultation = self.create_consultation()
        audio_reply = self.create_audio_reply(consultation)
        patient_url = reverse(
            "patient_portal_consultation_audio_reply_en",
            kwargs={"public_id": audio_reply.public_id},
        )
        staff_url = reverse(
            "dashboard_consultation_audio_reply",
            kwargs={"public_id": audio_reply.public_id},
        )

        with self.assertRaises(ValueError):
            _ = audio_reply.file.url

        anonymous_patient = self.client.get(patient_url)
        anonymous_staff = self.client.get(staff_url)
        self.assertEqual(anonymous_patient.status_code, 302)
        self.assertEqual(anonymous_staff.status_code, 302)

        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(patient_url).status_code, 404)
        self.assertEqual(self.client.get(staff_url).status_code, 403)

        self.client.force_login(self.patient_user)
        patient_response = self.client.get(patient_url)
        self.assertEqual(patient_response.status_code, 200)
        self.assertEqual(patient_response["Content-Type"], "audio/webm")
        self.assertIn("private", patient_response["Cache-Control"])
        self.assertIn("no-store", patient_response["Cache-Control"])
        self.assertEqual(patient_response["X-Content-Type-Options"], "nosniff")
        self.assertIn("inline", patient_response["Content-Disposition"])
        patient_response.close()

        detail = self.client.get(
            reverse(
                "patient_portal_consultation_detail_en",
                kwargs={"public_id": consultation.public_id},
            )
        )
        self.assertContains(detail, "Doctor Voice Reply")
        self.assertContains(detail, f'<source src="{patient_url}" type="audio/webm">')
        self.assertContains(detail, 'controls controlsList="nodownload"')
        self.assertContains(detail, "No text reply was added.")
        self.assertNotContains(detail, "autoplay")
        self.assertNotContains(detail, audio_reply.file.name)
        self.assertNotContains(detail, str(settings.PRIVATE_MEDIA_ROOT))
        self.assertNotContains(detail, f'href="{patient_url}"')

        self.client.force_login(self.staff)
        staff_response = self.client.get(staff_url)
        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(staff_response["Content-Type"], "audio/webm")
        staff_response.close()

    def test_recorder_ui_has_local_preview_timer_limits_and_no_upload_transport(self):
        consultation = self.create_consultation()
        self.client.force_login(self.staff)
        english = self.client.get(f"{self.staff_reply_url(consultation)}?lang=en")
        arabic = self.client.get(self.staff_reply_url(consultation))
        javascript = (settings.BASE_DIR / "static" / "js" / "consultation-recorder.js").read_text(
            encoding="utf-8"
        )

        for label in (
            "Start Recording",
            "Stop Recording",
            "Listen",
            "Record Again",
            "Remove Recording",
        ):
            self.assertContains(english, label)
        for label in ("بدء التسجيل", "إيقاف التسجيل", "استماع", "إعادة التسجيل", "حذف التسجيل"):
            self.assertContains(arabic, label)
        self.assertContains(english, 'data-max-duration-seconds="300"')
        self.assertContains(english, 'enctype="multipart/form-data"')
        self.assertContains(english, 'data-audio-local-preview hidden')
        self.assertContains(english, 'controls controlsList="nodownload"')
        self.assertNotContains(english, "autoplay")
        self.assertIn("navigator.mediaDevices.getUserMedia", javascript)
        self.assertIn("new MediaRecorder", javascript)
        self.assertIn("maxDurationSeconds * 1000", javascript)
        self.assertIn("new DataTransfer", javascript)
        self.assertIn("audioInput.files = transfer.files", javascript)
        self.assertIn("replyForm.addEventListener(\"submit\"", javascript)
        self.assertNotIn("fetch(", javascript)
        self.assertNotIn("XMLHttpRequest", javascript)

    def test_replacement_deletes_old_file_after_commit_and_keeps_one_current_reply(self):
        consultation = self.create_consultation()
        self.client.force_login(self.staff)
        self.client.post(
            self.staff_reply_url(consultation),
            {
                "staff_reply": "",
                "status": Consultation.Status.ANSWERED,
                "audio_reply": self.audio_upload(content=b"old-audio"),
            },
        )
        original = ConsultationAudioReply.objects.get(consultation=consultation)
        original_pk = original.pk
        original_public_id = original.public_id
        old_name = original.file.name
        storage = original.file.storage
        self.assertTrue(storage.exists(old_name))

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{self.staff_reply_url(consultation)}?lang=en",
                {
                    "staff_reply": "",
                    "status": Consultation.Status.ANSWERED,
                    "audio_reply": self.audio_upload(
                        name="replacement.ogg",
                        content_type="audio/ogg",
                        content=b"new-audio",
                    ),
                },
            )

        self.assertEqual(response.status_code, 302)
        replacement = ConsultationAudioReply.objects.get(consultation=consultation)
        self.assertEqual(replacement.pk, original_pk)
        self.assertEqual(replacement.public_id, original_public_id)
        self.assertEqual(replacement.content_type, "audio/ogg")
        self.assertEqual(ConsultationAudioReply.objects.filter(consultation=consultation).count(), 1)
        self.assertNotEqual(replacement.file.name, old_name)
        self.assertFalse(storage.exists(old_name))
        self.assertTrue(storage.exists(replacement.file.name))

    def test_removing_audio_deletes_storage_but_preserves_handled_timestamp_and_delete_lock(self):
        consultation = self.create_consultation()
        self.client.force_login(self.staff)
        self.client.post(
            self.staff_reply_url(consultation),
            {
                "staff_reply": "",
                "status": Consultation.Status.ANSWERED,
                "audio_reply": self.audio_upload(),
            },
        )
        consultation.refresh_from_db()
        handled_at = consultation.staff_handled_at
        audio_reply = ConsultationAudioReply.objects.get(consultation=consultation)
        stored_name = audio_reply.file.name
        storage = audio_reply.file.storage

        response = self.client.post(
            self.staff_reply_url(consultation),
            {
                "staff_reply": "",
                "status": Consultation.Status.CLOSED,
                "remove_audio": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        consultation.refresh_from_db()
        self.assertEqual(consultation.staff_handled_at, handled_at)
        self.assertFalse(ConsultationAudioReply.objects.filter(consultation=consultation).exists())
        self.assertFalse(storage.exists(stored_name))

        self.client.force_login(self.patient_user)
        delete_url = reverse(
            "patient_portal_consultation_delete_en",
            kwargs={"public_id": consultation.public_id},
        )
        self.assertEqual(self.client.get(delete_url).status_code, 404)
        detail = self.client.get(
            reverse(
                "patient_portal_consultation_detail_en",
                kwargs={"public_id": consultation.public_id},
            )
        )
        self.assertNotContains(detail, "Delete Consultation")

    def test_removal_storage_failure_rolls_back_reply_and_audio_changes(self):
        consultation = self.create_consultation()
        audio_reply = self.create_audio_reply(consultation)
        consultation.staff_reply = "Original reply"
        consultation.status = Consultation.Status.ANSWERED
        consultation.replied_by = self.staff
        consultation.replied_at = consultation.created_at
        consultation.staff_handled_at = consultation.created_at
        consultation.save()
        original_handled_at = consultation.staff_handled_at
        original_name = audio_reply.file.name
        self.client.force_login(self.staff)

        with patch.object(
            consultation_audio_reply_storage,
            "delete",
            side_effect=OSError("synthetic storage failure"),
        ):
            response = self.client.post(
                f"{self.staff_reply_url(consultation)}?lang=en",
                {
                    "staff_reply": "Changed reply",
                    "status": Consultation.Status.CLOSED,
                    "remove_audio": "on",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be removed safely")
        consultation.refresh_from_db()
        audio_reply.refresh_from_db()
        self.assertEqual(consultation.staff_reply, "Original reply")
        self.assertEqual(consultation.status, Consultation.Status.ANSWERED)
        self.assertEqual(consultation.staff_handled_at, original_handled_at)
        self.assertEqual(audio_reply.file.name, original_name)
        self.assertTrue(audio_reply.file.storage.exists(original_name))

    def test_missing_audio_file_returns_404(self):
        consultation = self.create_consultation()
        audio_reply = self.create_audio_reply(consultation)
        audio_reply.file.storage.delete(audio_reply.file.name)
        self.client.force_login(self.patient_user)

        response = self.client.get(
            reverse(
                "patient_portal_consultation_audio_reply",
                kwargs={"public_id": audio_reply.public_id},
            )
        )

        self.assertEqual(response.status_code, 404)
