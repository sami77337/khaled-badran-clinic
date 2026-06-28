import hashlib
from dataclasses import dataclass

from django.core.cache import cache

from apps.booking import services
from apps.core.models import SystemSetting


DEFAULT_BOOKING_POST_RATE_LIMIT_PER_HOUR = 10
DEFAULT_BOOKING_PHONE_RATE_LIMIT_PER_DAY = 5


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    message: str = ""


def _hash_identity(identity):
    normalized = str(identity or "unknown").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _increment_cache_counter(key, timeout):
    cache.add(key, 0, timeout=timeout)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return 1


def _rate_limit(scope, identity, *, limit, timeout, message):
    if limit <= 0:
        return RateLimitResult(True, 0, limit)
    key = f"booking-rate:{scope}:{_hash_identity(identity)}"
    count = _increment_cache_counter(key, timeout)
    if count > limit:
        return RateLimitResult(False, count, limit, message)
    return RateLimitResult(True, count, limit)


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def check_public_booking_ip_rate_limit(request):
    limit = services.get_integer_setting(
        SystemSetting.BOOKING_POST_RATE_LIMIT_PER_HOUR,
        DEFAULT_BOOKING_POST_RATE_LIMIT_PER_HOUR,
        minimum=1,
    )
    return _rate_limit(
        "ip-hour",
        get_client_ip(request),
        limit=limit,
        timeout=60 * 60,
        message="Too many booking attempts. Please wait before trying again.",
    )


def check_public_booking_phone_rate_limit(normalized_phone):
    limit = services.get_integer_setting(
        SystemSetting.BOOKING_PHONE_RATE_LIMIT_PER_DAY,
        DEFAULT_BOOKING_PHONE_RATE_LIMIT_PER_DAY,
        minimum=1,
    )
    return _rate_limit(
        "phone-day",
        normalized_phone,
        limit=limit,
        timeout=60 * 60 * 24,
        message="This phone number has reached the daily booking attempt limit.",
    )

