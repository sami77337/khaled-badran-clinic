"""Synthetic prefix bytes for content-signature tests; never use real patient media."""

SIGNATURES = {
    "image/jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/webp": b"RIFF\x14\x00\x00\x00WEBP",
    "video/mp4": b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isom",
    "application/pdf": b"%PDF-1.4\n",
    "audio/webm": b"\x1a\x45\xdf\xa3\x86\x82webm",
    "audio/ogg": b"OggS\x00",
    "audio/mp4": b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00isom",
}


def synthetic_media_bytes(content_type, payload=b"synthetic-content"):
    """A minimal matching header followed by synthetic text, not playable media."""
    mime = content_type.split(";", 1)[0].strip().lower()
    return SIGNATURES.get(mime, b"") + payload


def synthetic_media_bytes_of_size(content_type, size):
    """Return exactly size bytes for tests of length boundaries."""
    if size <= 0:
        return b""
    prefix = SIGNATURES.get(content_type, b"")
    if len(prefix) >= size:
        return prefix[:size]
    return prefix + b"x" * (size - len(prefix))
