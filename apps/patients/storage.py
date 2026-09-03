import uuid
from pathlib import PurePosixPath

from apps.records.storage import private_record_media_storage


def consultation_attachment_upload_path(instance, filename):
    extension = PurePosixPath(str(filename or "").replace("\\", "/")).suffix.lower()
    category = getattr(instance, "file_category", "") or "file"
    if category not in {"image", "short_video", "pdf"}:
        category = "file"
    return PurePosixPath(
        "consultations",
        category,
        str(instance.public_id),
        f"{uuid.uuid4().hex}{extension}",
    ).as_posix()


consultation_attachment_storage = private_record_media_storage
