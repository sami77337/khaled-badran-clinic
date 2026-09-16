"""Approved section definitions and fallback-aware public resolution."""

from itertools import groupby

from .models import DoctorPageSection


# key, Arabic title, English title, presentation, layout group
SECTION_DEFINITIONS = (
    ("experience", "الخبرة المهنية", "Professional Experience", "LIST", "professional"),
    ("education", "التعليم والتدريب", "Education & Training", "LIST", "professional"),
    ("boards", "البورد والشهادات", "Boards / Certifications", "LIST", "professional"),
    (
        "memberships",
        "العضويات المهنية",
        "Professional Memberships",
        "CHIPS",
        "professional",
    ),
    ("awards", "الجوائز", "Awards", "LIST", "professional"),
    ("languages", "اللغات", "Languages", "CHIPS", "professional"),
    ("specialties", "التخصصات", "Specialties", "CHIPS", "clinical"),
    (
        "conditions",
        "الحالات التي يعالجها الدكتور",
        "Conditions Treated",
        "CARDS",
        "clinical",
    ),
)
BUILTIN_SECTIONS = {row[0]: row for row in SECTION_DEFINITIONS}


def section_controls(doctor):
    rows = list(DoctorPageSection.objects.filter(doctor=doctor)) if doctor else []
    by_key = {row.key: row for row in rows if row.key}
    result = []
    for index, (key, ar, en, mode, group) in enumerate(SECTION_DEFINITIONS, 1):
        result.append(
            by_key.get(key)
            or DoctorPageSection(
                doctor=doctor,
                key=key,
                title_ar=ar,
                title_en=en,
                presentation=mode,
                display_order=index * 10,
            )
        )
    result.extend(row for row in rows if not row.key)
    return sorted(result, key=lambda row: (row.display_order, row.pk or 0, row.key))


def public_section_groups(doctor, language, content):
    result = []
    for row in section_controls(doctor):
        # This precedes fallback resolution: explicit hide/archive always wins.
        if not row.is_visible or row.is_archived:
            continue
        definition = BUILTIN_SECTIONS.get(row.key)
        if definition:
            values = content[row.key]
            title = (
                getattr(row, f"title_{language}").strip()
                or definition[1 if language == "ar" else 2]
            )
            membership_items = values if row.key == "memberships" else []
            lines = (
                [
                    " — ".join(
                        part for part in [item["label"], item["acronym"]] if part
                    )
                    for item in values
                ]
                if membership_items
                else values
            )
            group = definition[4]
        else:
            # Fail closed even for incomplete rows written outside the form.
            if not all(
                getattr(row, name).strip()
                for name in ("title_ar", "title_en", "content_ar", "content_en")
            ):
                continue
            title = getattr(row, f"title_{language}")
            lines = [
                line.strip()
                for line in getattr(row, f"content_{language}").splitlines()
                if line.strip()
            ]
            membership_items, group = [], "professional"
        result.append(
            {
                "key": row.key or f"custom-{row.pk}",
                "title": title,
                "mode": row.presentation,
                "lines": lines,
                "text": "\n".join(lines),
                "memberships": membership_items,
                "group": group,
            }
        )
    # Keep the original professional/clinical wrappers and their approved layout.
    # Reordered sections create contiguous groups in the requested global order.
    return [
        {"kind": key, "sections": list(rows)}
        for key, rows in groupby(result, key=lambda item: item["group"])
    ]
