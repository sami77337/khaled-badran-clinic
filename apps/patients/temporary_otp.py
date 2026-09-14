"""Temporary outage policy. Disabling the flag restores the existing OTP paths.

The group is a persistent unverified marker, never an authorization grant. Keep
it after rollback: switching off the mode does not verify existing accounts.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render

from apps.booking.phone import normalize_phone
from .profile_resolution import assert_profile_phone_available, resolve_authenticated_patient


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
    """Atomically create a new auth identity, medical profile and unverified marker."""
    from .account_otp import create_registration_user

    if not enabled():
        raise ValidationError("Temporary registration is unavailable.")
    phone = normalize_phone(phone)
    assert_profile_phone_available(phone)
    group, _ = Group.objects.get_or_create(name=UNVERIFIED_GROUP)
    if group.permissions.exists():
        raise ValidationError("Registration unavailable.")
    user = create_registration_user(phone, registration)
    resolve_authenticated_patient(user, full_name=registration["full_name"])
    user.groups.add(group)
    return user


def is_unverified(user):
    return user.groups.filter(name=UNVERIFIED_GROUP).exists()


def backfill_unverified_profiles(*, apply=False):
    """Counts only; every candidate is rechecked and isolated in a transaction."""
    candidates = get_user_model().objects.filter(
        groups__name=UNVERIFIED_GROUP,
        is_active=True,
        is_staff=False,
        is_superuser=False,
        patient_profile__isnull=True,
    ).order_by("pk")
    counts = dict(candidates=0, created=0, would_create=0, skipped_conflict=0,
                  skipped_ineligible=0, failed=0)
    for user_id in candidates.values_list("pk", flat=True).iterator():
        counts["candidates"] += 1
        try:
            with transaction.atomic():
                user = get_user_model().objects.select_for_update().filter(pk=user_id).first()
                if (
                    user is None or not user.is_active or user.is_staff or user.is_superuser
                    or not is_unverified(user) or hasattr(user, "patient_profile")
                ):
                    counts["skipped_ineligible"] += 1
                    continue
                assert_profile_phone_available(user.username, user=user)
                if apply:
                    resolve_authenticated_patient(user)
            counts["created" if apply else "would_create"] += 1
        except ValidationError:
            counts["skipped_conflict"] += 1
        except Exception:
            # Never print database exception text: it may contain patient data.
            counts["failed"] += 1
    return counts
