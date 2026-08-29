import re


PUBLIC_CASE_ROLE_BEFORE = "before"
PUBLIC_CASE_ROLE_AFTER = "after"
PUBLIC_CASE_ROLE_VIDEO = "video"
PUBLIC_CASE_ROLE_VIDEO_COVER = "video_cover"

PUBLIC_CASE_ROLES = {
    PUBLIC_CASE_ROLE_BEFORE,
    PUBLIC_CASE_ROLE_AFTER,
    PUBLIC_CASE_ROLE_VIDEO,
    PUBLIC_CASE_ROLE_VIDEO_COVER,
}

_ROLE_TITLE_PATTERN = re.compile(
    r"^\[\[public-case:(before|after|video|video_cover)\]\](.*)$",
    re.DOTALL,
)


def encode_public_case_title(role, public_title):
    if role not in PUBLIC_CASE_ROLES:
        raise ValueError("Unsupported public case media role.")
    clean_title = (public_title or "").strip()
    return f"[[public-case:{role}]]{clean_title}"


def decode_public_case_title(stored_title):
    """Return (role, clean public title, is_encoded) for new and legacy rows."""
    title = (stored_title or "").strip()
    match = _ROLE_TITLE_PATTERN.match(title)
    if match:
        return match.group(1), match.group(2).strip(), True

    normalized = title.casefold()
    legacy_roles = (
        ("before", PUBLIC_CASE_ROLE_BEFORE),
        ("قبل", PUBLIC_CASE_ROLE_BEFORE),
        ("after", PUBLIC_CASE_ROLE_AFTER),
        ("بعد", PUBLIC_CASE_ROLE_AFTER),
    )
    for marker, role in legacy_roles:
        if normalized == marker:
            return role, "", False
        prefix = f"{marker} "
        if normalized.startswith(prefix):
            return role, title[len(prefix) :].strip(), False

    return "primary", title, False
