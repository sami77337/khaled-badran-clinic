import os
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import transaction
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


def public_case_media_upload_path(instance, filename):
    public_id = getattr(instance, "public_id", None) or uuid.uuid4()
    media_type = getattr(instance, "media_type", "") or "media"
    if media_type not in {"image", "short_video"}:
        media_type = "media"

    return PurePosixPath(
        "public-cases",
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


@deconstructible
class PublicCaseMediaStorage(FileSystemStorage):
    @property
    def base_location(self):
        return os.fspath(settings.PUBLIC_CASE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None

    def url(self, name):
        raise ValueError("Public-case media files are available only through protected routes.")


public_case_media_storage = PublicCaseMediaStorage()


class PublicCaseMediaStorageDeletionError(RuntimeError):
    """Raised after commit when marketing storage cleanup is incomplete."""


def _delete_public_case_media_files(file_references):
    failure_count = 0
    for storage, name in file_references:
        try:
            storage.delete(name)
        except Exception:  # Storage backends expose provider-specific deletion errors.
            failure_count += 1
    if failure_count:
        raise PublicCaseMediaStorageDeletionError(
            f"Marketing media cleanup failed for {failure_count} storage object(s)."
        )


def schedule_public_case_media_file_deletion(media_items):
    """Delete captured marketing files only after the surrounding DB commit succeeds."""
    file_references = []
    seen = set()
    for media in media_items:
        if not media.file or not media.file.name:
            continue
        reference_key = (id(media.file.storage), media.file.name)
        if reference_key in seen:
            continue
        seen.add(reference_key)
        file_references.append((media.file.storage, media.file.name))

    if file_references:
        transaction.on_commit(lambda: _delete_public_case_media_files(file_references))
    return len(file_references)
