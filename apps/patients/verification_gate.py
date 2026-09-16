from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from apps.patients import phone_change, rate_limits, temporary_otp
from apps.patients.models import AccountPhoneChangeChallenge
from apps.patients.otp import WhatsAppOtpServiceUnavailable


_PORTAL_PREFIXES = ("/portal/", "/en/portal/")
_VERIFICATION_PATHS = {
    "/portal/password/change/",
    "/en/portal/password/change/",
}
_LOGOUT_PATHS = {
    "/portal/logout/",
    "/en/portal/logout/",
}
_LOGIN_PATHS = {
    "/login/",
    "/en/login/",
    "/portal/login/",
    "/en/portal/login/",
}


def _language_for_request(request):
    return "en" if request.path.startswith("/en/") else "ar"


def _verification_url(language):
    return reverse(
        "patient_portal_password_change_en"
        if language == "en"
        else "patient_portal_password_change"
    )


def _requires_phone_verification(request):
    user = getattr(request, "user", None)
    return bool(
        not temporary_otp.enabled()
        and user is not None
        and user.is_authenticated
        and not user.is_staff
        and not user.is_superuser
        and temporary_otp.is_unverified(user)
    )


def _is_patient_portal_path(path):
    return path.startswith(_PORTAL_PREFIXES)


def _may_access_while_unverified(path):
    return path in _VERIFICATION_PATHS or path in _LOGOUT_PATHS


def _active_current_phone_challenge(user):
    return (
        AccountPhoneChangeChallenge.objects.filter(
            user=user,
            phone_e164=user.username,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


def _ensure_current_phone_challenge(request, language):
    if _active_current_phone_challenge(request.user) is not None:
        return

    attempt_limit = rate_limits.check_phone_change_start_rate_limit(request)
    if not attempt_limit.allowed:
        messages.error(
            request,
            "عدد محاولات التحقق كبير. حاول لاحقًا."
            if language == "ar"
            else "Too many verification requests. Please try again later.",
        )
        return

    try:
        phone_change.start_current_phone_verification(
            user=request.user,
            language=language,
        )
    except (WhatsAppOtpServiceUnavailable, phone_change.PhoneChangeConflictError):
        messages.error(request, temporary_otp.unavailable_message(language))
    else:
        messages.success(
            request,
            "تم إرسال رمز التحقق عبر واتساب إلى رقم حسابك الحالي."
            if language == "ar"
            else "A WhatsApp verification code was sent to your current account phone.",
        )


class LegacyPatientOtpGateMiddleware:
    """Require real OTP verification for accounts created during Temporary Mode.

    The persistent ``patient_phone_unverified_temporary`` marker is the source of
    truth. This middleware never marks a phone verified itself; the existing
    ``verify_account_phone_change`` transaction remains the only path that clears
    that marker after a successful real OTP.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = _language_for_request(request)

        # Gate already-authenticated legacy sessions before any private portal view
        # executes. The verification page and logout remain reachable.
        if (
            _requires_phone_verification(request)
            and _is_patient_portal_path(request.path)
            and not _may_access_while_unverified(request.path)
        ):
            _ensure_current_phone_challenge(request, language)
            return redirect(_verification_url(language))

        response = self.get_response(request)

        # A login request starts anonymous. Re-check after the view because
        # auth_login() updates request.user only after valid credentials succeed.
        if (
            request.path in _LOGIN_PATHS
            and _requires_phone_verification(request)
        ):
            _ensure_current_phone_challenge(request, language)
            return redirect(_verification_url(language))

        return response
