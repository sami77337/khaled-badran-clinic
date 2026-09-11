from django import template

from apps.core.models import DoctorPageContent


register = template.Library()


def _lines(value):
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _memberships(value):
    rows = []
    for line in _lines(value):
        if "|" in line:
            label, acronym = (part.strip() for part in line.split("|", 1))
        else:
            label, acronym = "", line.strip()
        if acronym:
            rows.append({"label": label, "acronym": acronym})
    return rows


@register.simple_tag
def doctor_public_content(doctor, language="ar"):
    """Return doctor-page content, preferring owner-edited database copy.

    Blank editable fields deliberately fall back to the approved hard-coded
    content so a partially edited profile never removes existing information.
    """
    from apps.core.views import DOCTOR_CONDITIONS, DOCTOR_DEFAULT, DOCTOR_PUBLIC_PROFILE

    language = "en" if language == "en" else "ar"
    fallback = {
        **DOCTOR_PUBLIC_PROFILE[language],
        "conditions": DOCTOR_CONDITIONS[language],
        "hero_summary": DOCTOR_DEFAULT[f"hero_summary_{language}"],
        "bio": DOCTOR_DEFAULT[f"bio_{language}"],
    }
    if doctor is None:
        return fallback

    content = DoctorPageContent.objects.filter(doctor=doctor).first()
    if content is None:
        return fallback

    scalar_map = {
        "hero_summary": getattr(content, f"hero_summary_{language}"),
        "bio": getattr(content, f"professional_bio_{language}"),
    }
    list_fields = (
        "experience",
        "education",
        "boards",
        "awards",
        "languages",
        "specialties",
        "conditions",
    )
    result = dict(fallback)
    for key, value in scalar_map.items():
        if (value or "").strip():
            result[key] = value.strip()
    for key in list_fields:
        values = _lines(getattr(content, f"{key}_{language}"))
        if values:
            result[key] = values
    memberships = _memberships(getattr(content, f"memberships_{language}"))
    if memberships:
        result["memberships"] = memberships
    return result
