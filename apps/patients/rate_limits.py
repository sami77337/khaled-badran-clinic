import hashlib
from dataclasses import dataclass

from django.core.cache import cache

from apps.booking.rate_limits import get_client_ip


DEFAULT_PORTAL_LINK_ATTEMPTS_PER_HOUR = 10


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    message: str = ""


def _hash_identity(identity):
    return hashlib.sha256(str(identity or "unknown").encode("utf-8")).hexdigest()


def _increment_cache_counter(key, timeout):
    cache.add(key, 0, timeout=timeout)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return 1


def check_link_attempt_rate_limit(request):
    identity = f"user:{request.user.pk}:ip:{get_client_ip(request)}"
    key = f"patient-portal-link-hour:{_hash_identity(identity)}"
    count = _increment_cache_counter(key, timeout=60 * 60)
    if count > DEFAULT_PORTAL_LINK_ATTEMPTS_PER_HOUR:
        return RateLimitResult(
            allowed=False,
            count=count,
            limit=DEFAULT_PORTAL_LINK_ATTEMPTS_PER_HOUR,
            message="Too many appointment link attempts. Please wait before trying again.",
        )
    return RateLimitResult(True, count, DEFAULT_PORTAL_LINK_ATTEMPTS_PER_HOUR)
