import os
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


def _suffix_from_filename(filename):
    return PurePosixPath(str(filename or "").replace("\\", "/")).suffix.lower()


def private_record_media_upload_path(instance, filename):
    public_id = getattr(instance, "public_id", None) or uuid.uuid4()
    media_type = getattr(instance, "media_type", "") or "media"
    if media_type not in {"image", "short_video"}:
        media_type = "media"

    return PurePosixPath(
        "records",
        media_type,
        str(public_id),
        f"{uuid.uuid4().hex}{_suffix_from_filename(filename)}",
    ).as_posix()


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    @property
    def base_location(self):
        return os.fspath(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Private medical media files are not publicly URL-addressable.")


private_record_media_storage = PrivateMediaStorage()
