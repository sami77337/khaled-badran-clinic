import hashlib
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from apps.booking.rate_limits import get_client_ip
from apps.booking.phone import normalize_phone


DEFAULT_PORTAL_LINK_ATTEMPTS_PER_HOUR = 12
DEFAULT_PORTAL_LINK_PHONE_ATTEMPTS_PER_HOUR = 12
DEFAULT_PORTAL_LOGIN_IP_ATTEMPTS_PER_WINDOW = 30
DEFAULT_PORTAL_LOGIN_PHONE_ATTEMPTS_PER_WINDOW = 15
DEFAULT_PORTAL_REGISTRATION_IP_ATTEMPTS_PER_HOUR = 20
DEFAULT_PORTAL_REGISTRATION_PHONE_ATTEMPTS_PER_DAY = 8

PORTAL_LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
GENERIC_PORTAL_RATE_LIMIT_MESSAGE = "Too many portal attempts. Please wait before trying again."
GENERIC_LINK_RATE_LIMIT_MESSAGE = "Too many appointment link attempts. Please wait before trying again."


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    message: str = ""


def _hash_identity(identity):
    normalized = str(identity or "unknown").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_rate_limit_cache_key(scope, identity):
    return f"patient-portal-rate:{scope}:{_hash_identity(identity)}"


def _increment_cache_counter(key, timeout):
    cache.add(key, 0, timeout=timeout)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return 1


def _setting_int(name, default):
    try:
        value = int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _rate_limit(scope, identity, *, limit, timeout, message):
    key = build_rate_limit_cache_key(scope, identity)
    count = _increment_cache_counter(key, timeout=timeout)
    if count > limit:
        return RateLimitResult(False, count, limit, message)
    return RateLimitResult(True, count, limit)


def _first_blocked(results):
    for result in results:
        if not result.allowed:
            return result
    return results[-1] if results else RateLimitResult(True, 0, 0)


def normalized_phone_or_empty(raw_phone):
    try:
        return normalize_phone(raw_phone)
    except ValidationError:
        return ""


def _ip_identity(request):
    return f"ip:{get_client_ip(request)}"


def _user_ip_identity(request):
    user_pk = getattr(getattr(request, "user", None), "pk", None) or "anonymous"
    return f"user:{user_pk}:ip:{get_client_ip(request)}"


def check_link_attempt_rate_limit(request, *, normalized_phone=""):
    results = [
        _rate_limit(
            "link-user-ip-hour",
            _user_ip_identity(request),
            limit=_setting_int(
                "PATIENT_PORTAL_LINK_ATTEMPTS_PER_HOUR",
                DEFAULT_PORTAL_LINK_ATTEMPTS_PER_HOUR,
            ),
            timeout=60 * 60,
            message=GENERIC_LINK_RATE_LIMIT_MESSAGE,
        )
    ]

    if normalized_phone:
        results.append(
            _rate_limit(
                "link-phone-hour",
                normalized_phone,
                limit=_setting_int(
                    "PATIENT_PORTAL_LINK_PHONE_ATTEMPTS_PER_HOUR",
                    DEFAULT_PORTAL_LINK_PHONE_ATTEMPTS_PER_HOUR,
                ),
                timeout=60 * 60,
                message=GENERIC_LINK_RATE_LIMIT_MESSAGE,
            )
        )

    return _first_blocked(results)


def check_login_attempt_rate_limit(request, *, normalized_phone=""):
    results = [
        _rate_limit(
            "login-ip-window",
            _ip_identity(request),
            limit=_setting_int(
                "PATIENT_PORTAL_LOGIN_IP_ATTEMPTS_PER_WINDOW",
                DEFAULT_PORTAL_LOGIN_IP_ATTEMPTS_PER_WINDOW,
            ),
            timeout=PORTAL_LOGIN_RATE_LIMIT_WINDOW_SECONDS,
            message=GENERIC_PORTAL_RATE_LIMIT_MESSAGE,
        )
    ]

    if normalized_phone:
        results.append(
            _rate_limit(
                "login-phone-window",
                normalized_phone,
                limit=_setting_int(
                    "PATIENT_PORTAL_LOGIN_PHONE_ATTEMPTS_PER_WINDOW",
                    DEFAULT_PORTAL_LOGIN_PHONE_ATTEMPTS_PER_WINDOW,
                ),
                timeout=PORTAL_LOGIN_RATE_LIMIT_WINDOW_SECONDS,
                message=GENERIC_PORTAL_RATE_LIMIT_MESSAGE,
            )
        )

    return _first_blocked(results)


def check_registration_attempt_rate_limit(request, *, normalized_phone=""):
    results = [
        _rate_limit(
            "registration-ip-hour",
            _ip_identity(request),
            limit=_setting_int(
                "PATIENT_PORTAL_REGISTRATION_IP_ATTEMPTS_PER_HOUR",
                DEFAULT_PORTAL_REGISTRATION_IP_ATTEMPTS_PER_HOUR,
            ),
            timeout=60 * 60,
            message=GENERIC_PORTAL_RATE_LIMIT_MESSAGE,
        )
    ]

    if normalized_phone:
        results.append(
            _rate_limit(
                "registration-phone-day",
                normalized_phone,
                limit=_setting_int(
                    "PATIENT_PORTAL_REGISTRATION_PHONE_ATTEMPTS_PER_DAY",
                    DEFAULT_PORTAL_REGISTRATION_PHONE_ATTEMPTS_PER_DAY,
                ),
                timeout=60 * 60 * 24,
                message=GENERIC_PORTAL_RATE_LIMIT_MESSAGE,
            )
        )

    return _first_blocked(results)


def check_consultation_submission_rate_limit(request):
    return _rate_limit(
        "consultation-submit",
        _user_ip_identity(request),
        limit=_setting_int("PATIENT_CONSULTATION_RATE_LIMIT_PER_HOUR", 5),
        timeout=60 * 60,
        message="Too many consultation submissions. Please try again later.",
    )


def check_phone_change_start_rate_limit(request):
    return _rate_limit(
        "phone-change-start",
        _user_ip_identity(request),
        limit=_setting_int("ACCOUNT_PHONE_CHANGE_START_RATE_LIMIT_PER_HOUR", 5),
        timeout=60 * 60,
        message="Too many phone verification requests. Please try again later.",
    )


def check_phone_change_resend_rate_limit(request):
    return _rate_limit(
        "phone-change-resend",
        _user_ip_identity(request),
        limit=_setting_int("ACCOUNT_PHONE_CHANGE_RESEND_RATE_LIMIT_PER_HOUR", 5),
        timeout=60 * 60,
        message="Too many verification-code requests. Please try again later.",
    )


def check_phone_change_verify_rate_limit(request):
    return _rate_limit(
        "phone-change-verify",
        _user_ip_identity(request),
        limit=_setting_int("ACCOUNT_PHONE_CHANGE_VERIFY_RATE_LIMIT_PER_HOUR", 20),
        timeout=60 * 60,
        message="Too many verification attempts. Please try again later.",
    )


def check_link_recovery_start_rate_limit(request, *, normalized_phone=""):
    results = [
        _rate_limit(
            "link-recovery-start-user-ip",
            _user_ip_identity(request),
            limit=_setting_int("APPOINTMENT_LINK_RECOVERY_START_RATE_LIMIT_PER_HOUR", 5),
            timeout=60 * 60,
            message=GENERIC_LINK_RATE_LIMIT_MESSAGE,
        )
    ]
    if normalized_phone:
        results.append(
            _rate_limit(
                "link-recovery-start-phone",
                normalized_phone,
                limit=_setting_int(
                    "APPOINTMENT_LINK_RECOVERY_PHONE_RATE_LIMIT_PER_HOUR",
                    5,
                ),
                timeout=60 * 60,
                message=GENERIC_LINK_RATE_LIMIT_MESSAGE,
            )
        )
    return _first_blocked(results)


def check_link_recovery_resend_rate_limit(request):
    return _rate_limit(
        "link-recovery-resend",
        _user_ip_identity(request),
        limit=_setting_int("APPOINTMENT_LINK_RECOVERY_RESEND_RATE_LIMIT_PER_HOUR", 5),
        timeout=60 * 60,
        message=GENERIC_LINK_RATE_LIMIT_MESSAGE,
    )


def check_link_recovery_verify_rate_limit(request):
    return _rate_limit(
        "link-recovery-verify",
        _user_ip_identity(request),
        limit=_setting_int("APPOINTMENT_LINK_RECOVERY_VERIFY_RATE_LIMIT_PER_HOUR", 20),
        timeout=60 * 60,
        message=GENERIC_LINK_RATE_LIMIT_MESSAGE,
    )
