"""Synthetic-only content-signature and bounded upload verification tests."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.patients.models import (
    CONSULTATION_AUDIO_MAX_BYTES,
    CONSULTATION_IMAGE_MAX_BYTES,
    validate_consultation_audio_upload,
    validate_consultation_upload,
)
from apps.patients.test_upload_fixtures import synthetic_media_bytes


class ConsultationUploadContentValidationTests(SimpleTestCase):
    def upload(self, name, mime, payload=None):
        return SimpleUploadedFile(
            name,
            synthetic_media_bytes(mime) if payload is None else payload,
            content_type=mime,
        )

    def test_supported_attachment_signatures_match_extension_and_mime(self):
        for name, mime, category in (
            ("synthetic.jpg", "image/jpeg", "image"),
            ("synthetic.jpeg", "image/jpeg", "image"),
            ("synthetic.png", "image/png", "image"),
            ("synthetic.webp", "image/webp", "image"),
            ("synthetic.mp4", "video/mp4", "short_video"),
            ("synthetic.pdf", "application/pdf", "pdf"),
        ):
            with self.subTest(name=name):
                upload = self.upload(name, mime)
                upload.seek(3)
                metadata = validate_consultation_upload(upload)
                self.assertEqual(metadata["file_category"], category)
                self.assertEqual(metadata["file_size"], upload.size)
                self.assertEqual(upload.tell(), 3)

    def test_supported_audio_signatures_include_browser_mime_parameters(self):
        for name, mime in (
            ("reply.webm", "audio/webm"),
            ("reply.webm", "audio/webm;codecs=opus"),
            ("reply.ogg", "audio/ogg"),
            ("reply.m4a", "audio/mp4"),
            ("reply.mp4", "audio/mp4"),
        ):
            with self.subTest(name=name):
                upload = self.upload(name, mime)
                upload.seek(2)
                metadata = validate_consultation_audio_upload(upload)
                self.assertEqual(metadata["content_type"], mime.split(";", 1)[0])
                self.assertEqual(upload.tell(), 2)

    def test_mismatched_content_is_rejected_without_echoing_payload_or_filename(self):
        for name, mime, checker in (
            ("private.jpg", "image/jpeg", validate_consultation_upload),
            ("private.png", "image/png", validate_consultation_upload),
            ("private.webp", "image/webp", validate_consultation_upload),
            ("private.mp4", "video/mp4", validate_consultation_upload),
            ("private.pdf", "application/pdf", validate_consultation_upload),
            ("voice.webm", "audio/webm", validate_consultation_audio_upload),
            ("voice.ogg", "audio/ogg", validate_consultation_audio_upload),
            ("voice.m4a", "audio/mp4", validate_consultation_audio_upload),
        ):
            with self.subTest(name=name):
                fake = self.upload(name, mime, payload=b"<html>PRIVATE_SYNTHETIC_CONTENT</html>")
                fake.seek(5)
                with self.assertRaises(ValidationError) as raised:
                    checker(fake)
                self.assertNotIn(name, str(raised.exception))
                self.assertNotIn("PRIVATE_SYNTHETIC_CONTENT", str(raised.exception))
                self.assertEqual(fake.tell(), 5)

    def test_header_matching_mime_with_wrong_extension_is_rejected(self):
        mismatched = self.upload(
            "synthetic.jpg", "image/png",
            payload=synthetic_media_bytes("image/png"),
        )
        with self.assertRaises(ValidationError):
            validate_consultation_upload(mismatched)
        audio = self.upload("reply.ogg", "audio/webm")
        with self.assertRaises(ValidationError):
            validate_consultation_audio_upload(audio)

    def test_declared_length_forgery_and_empty_file_fail_closed(self):
        short = self.upload("private.pdf", "application/pdf")
        short.size = 8
        with self.assertRaises(ValidationError):
            validate_consultation_upload(short)
        too_long = self.upload("private.jpg", "image/jpeg")
        too_long.size = CONSULTATION_IMAGE_MAX_BYTES + 1
        with self.assertRaises(ValidationError):
            validate_consultation_upload(too_long)
        audio = self.upload("reply.ogg", "audio/ogg")
        audio.size = CONSULTATION_AUDIO_MAX_BYTES + 1
        with self.assertRaises(ValidationError):
            validate_consultation_audio_upload(audio)
        empty = self.upload("private.pdf", "application/pdf", payload=b"")
        with self.assertRaises(ValidationError):
            validate_consultation_upload(empty)

    def test_unreadable_and_unseekable_uploads_are_rejected(self):
        file = self.upload("private.jpg", "image/jpeg")
        with patch.object(file, "tell", side_effect=OSError("synthetic IO problem")):
            with self.assertRaises(ValidationError):
                validate_consultation_upload(file)
        file = self.upload("private.pdf", "application/pdf")
        with patch.object(file, "read", side_effect=OSError("synthetic IO problem")):
            with self.assertRaises(ValidationError):
                validate_consultation_upload(file)

    def test_signature_inspection_never_reads_unbounded_file_content(self):
        upload = self.upload("private.mp4", "video/mp4", payload=synthetic_media_bytes("video/mp4", b"x" * 65536))
        upload.seek(29)
        with patch.object(upload, "read", wraps=upload.read) as read:
            meta = validate_consultation_upload(upload)
        self.assertEqual(meta["file_size"], upload.size)
        self.assertEqual(upload.tell(), 29)
        self.assertEqual(read.call_args_list[0].args, (4096,))
