from django import template
from django.templatetags.static import static
from django.urls import reverse

from apps.core.models import DoctorPageContent


register = template.Library()


@register.simple_tag
def doctor_section_groups(doctor, language, content):
    from apps.core.doctor_sections import public_section_groups
    return public_section_groups(doctor, language, content)


@register.simple_tag
def doctor_photo_url(doctor):
    if doctor is not None:
        content = DoctorPageContent.objects.filter(doctor=doctor).only("profile_photo").first()
        if content is not None and content.profile_photo and content.profile_photo.name:
            return reverse("dashboard_doctor_public_photo")
    return static("img/doctor/dr-khaled-badran.png")


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


def doctor_default_content(doctor, language="ar"):
    """Return the actual blank-field fallback for rendering and editor hints."""
    from apps.core.views import DOCTOR_CONDITIONS, DOCTOR_DEFAULT, DOCTOR_PUBLIC_PROFILE

    language = "en" if language == "en" else "ar"
    return {
        **DOCTOR_PUBLIC_PROFILE[language],
        "conditions": DOCTOR_CONDITIONS[language],
        "hero_summary": DOCTOR_DEFAULT[f"hero_summary_{language}"],
        "bio": (
            getattr(doctor, f"bio_{language}", "") or DOCTOR_DEFAULT[f"bio_{language}"]
        ),
        "credential_label": DOCTOR_DEFAULT[f"credential_label_{language}"],
    }


@register.simple_tag
def doctor_public_content(doctor, language="ar"):
    """Return doctor-page content, preferring owner-edited database copy.

    Blank editable fields deliberately fall back to the approved hard-coded
    content so a partially edited profile never removes existing information.
    """
    language = "en" if language == "en" else "ar"
    fallback = doctor_default_content(doctor, language)
    if doctor is None:
        return fallback

    content = DoctorPageContent.objects.filter(doctor=doctor).first()
    if content is None:
        return fallback

    scalar_map = {
        "hero_summary": getattr(content, f"hero_summary_{language}"),
        "bio": getattr(content, f"professional_bio_{language}"),
        "credential_label": getattr(content, f"credential_label_{language}"),
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
