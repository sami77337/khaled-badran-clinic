import logging
import os
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.utils.deconstruct import deconstructible


logger = logging.getLogger(__name__)
MAX_DOCTOR_PHOTO_BYTES = 8 * 1024 * 1024
_ALLOWED_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _suffix(filename):
    return PurePosixPath(str(filename or "").replace("\\", "/")).suffix.lower()


def doctor_photo_upload_path(instance, filename):
    doctor_id = getattr(instance, "doctor_id", None) or "doctor"
    return PurePosixPath(
        "doctor",
        str(doctor_id),
        f"{uuid.uuid4().hex}{_suffix(filename)}",
    ).as_posix()


def _detect_image_content_type(uploaded_file):
    position = uploaded_file.tell()
    header = uploaded_file.read(16)
    uploaded_file.seek(position)
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return ""


def validate_doctor_photo_upload(uploaded_file, language="ar"):
    is_arabic = language != "en"
    if not uploaded_file or not getattr(uploaded_file, "size", 0):
        raise ValidationError(
            "اختر ملف صورة صالحًا." if is_arabic else "Choose a valid image file."
        )
    if uploaded_file.size > MAX_DOCTOR_PHOTO_BYTES:
        raise ValidationError(
            "حجم الصورة يجب ألا يتجاوز 8 ميجابايت."
            if is_arabic
            else "The image must not exceed 8 MB."
        )
    content_type = _detect_image_content_type(uploaded_file)
    extension = _suffix(getattr(uploaded_file, "name", ""))
    if not content_type or _ALLOWED_EXTENSIONS.get(extension) != content_type:
        raise ValidationError(
            "الصيغ المسموحة: JPG وPNG وWebP فقط."
            if is_arabic
            else "Only JPG, PNG and WebP images are allowed."
        )
    return content_type


@deconstructible
class PublicSiteMediaStorage(FileSystemStorage):
    """Durable site-owned public media kept outside static files.

    Files are stored under the existing persistent media root but intentionally
    have no direct URL. Only explicit public-site views may serve them.
    """

    @property
    def base_location(self):
        return os.path.join(os.fspath(settings.PRIVATE_MEDIA_ROOT), "public-site")

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Public site media is served only through controlled routes.")


public_site_media_storage = PublicSiteMediaStorage()


def schedule_public_site_file_deletion(storage, name):
    if not name:
        return

    def cleanup():
        try:
            storage.delete(name)
        except Exception:
            logger.warning("Public site media cleanup failed.")

    transaction.on_commit(cleanup)
