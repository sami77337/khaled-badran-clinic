"""Temporary outage policy. Disabling the flag restores the existing OTP paths.

The group is a persistent unverified marker, never an authorization grant. Keep
it after rollback: switching off the mode does not verify existing accounts.
"""

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render

from apps.booking.phone import normalize_phone


UNVERIFIED_GROUP = "patient_phone_unverified_temporary"


def enabled():
    return getattr(settings, "PATIENT_OTP_TEMPORARY_MODE", False)


def unavailable_message(language):
    return (
        "هذه الخدمة غير متاحة مؤقتًا. يرجى المحاولة لاحقًا أو التواصل مع العيادة."
        if language == "ar"
        else "This service is temporarily unavailable. Please try again later or contact the clinic."
    )


def unavailable_response(request, language):
    from .views import _portal_context

    context = _portal_context(request, language)
    context["auth_language_url"] = context["portal_language_switch_url"]
    context["page_title"] = (
        "الخدمة غير متاحة مؤقتًا" if language == "ar" else "Service temporarily unavailable"
    )
    response = render(request, "patients/otp_temporarily_unavailable.html", context, status=503)
    response["Cache-Control"] = "private, no-store"
    return response


@transaction.atomic
def create_unverified_account(*, phone, registration):
    """Create only an isolated auth identity from already validated form data."""
    from .account_otp import _phone_taken, create_registration_user
    from .models import Patient

    if not enabled():
        raise ValidationError("Temporary registration is unavailable.")
    phone = normalize_phone(phone)
    if _phone_taken(phone) or Patient.objects.filter(phone_e164=phone).exists():
        raise ValidationError("Registration unavailable.")
    # Older staff-created records may have only a raw phone. They must not be
    # silently overlooked just because the canonical field is blank.
    for raw in Patient.objects.filter(phone_e164="").values_list("phone_raw", flat=True).iterator():
        try:
            matched = normalize_phone(raw) == phone
        except ValidationError:
            continue
        if matched:
            raise ValidationError("Registration unavailable.")
    group, _ = Group.objects.get_or_create(name=UNVERIFIED_GROUP)
    if group.permissions.exists():
        raise ValidationError("Registration unavailable.")
    user = create_registration_user(phone, registration)
    user.groups.add(group)
    return user
