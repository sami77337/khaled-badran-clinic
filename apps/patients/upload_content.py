"""Bounded content-signature checks for newly submitted private clinical uploads.

This is format sniffing, not full media decoding, antivirus scanning, or a
guarantee that a media container is well formed. Never open stored patient
files here; only inspect the incoming temporary upload before storage.
"""

from pathlib import PurePosixPath

from django.core.exceptions import ValidationError


# The table prevents e.g. a PNG with a .jpg name even if both are "image".
_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",  # audio/mp4 permitted explicitly below
}


def _matches_signature(header, content_type):
    if content_type == "image/jpeg":
        return header.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if content_type == "application/pdf":
        return header.startswith(b"%PDF-")
    if content_type in ("video/mp4", "audio/mp4"):
        return (
            len(header) >= 12
            and header[4:8] == b"ftyp"
            and int.from_bytes(header[:4], "big") >= 12
        )
    if content_type == "audio/webm":
        return header.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in header[:4096]
    if content_type == "audio/ogg":
        return header.startswith(b"OggS\x00")
    return False


def validate_private_upload_content(uploaded_file, *, filename, content_type, size, max_bytes):
    """Validate MIME/extension and bounded content signature; restore seek position.

    Read at most 4 KiB plus a constant-size stream length check; do not load a
    50 MiB attachment into memory. An inaccessible/unseekable upload fails
    closed rather than being stored without inspection. Error messages and
    caller logs must not contain the original filename or byte contents.
    """
    ext = PurePosixPath(str(filename).replace("\\", "/")).suffix.lower()
    expected_mime = _EXT_TO_MIME.get(ext)
    allowed_mp4_audio = ext == ".mp4" and content_type == "audio/mp4"
    if not expected_mime or (
        expected_mime != content_type and not allowed_mp4_audio
    ):
        raise ValidationError("Uploaded file type does not match its extension.")
    if not isinstance(size, int) or size <= 0 or size > max_bytes:
        raise ValidationError("Uploaded file exceeds its size policy.")

    original_position = None
    failed = False
    header = b""
    actual_size = None
    try:
        original_position = uploaded_file.tell()
        uploaded_file.seek(0)
        header = uploaded_file.read(4096)
        uploaded_file.seek(0, 2)
        actual_size = uploaded_file.tell()
    except (OSError, ValueError, AttributeError, TypeError):
        failed = True
    finally:
        if original_position is not None:
            try:
                uploaded_file.seek(original_position)
            except (OSError, ValueError, AttributeError, TypeError):
                failed = True

    if failed or actual_size != size or actual_size > max_bytes:
        raise ValidationError("Uploaded file could not be verified.")
    if not _matches_signature(header, content_type):
        raise ValidationError("Uploaded file content does not match its declared type.")
