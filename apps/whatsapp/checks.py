from django.conf import settings
from django.core.checks import Error, Tags, register

from .configuration import configuration_issues


@register(Tags.security)
def meta_configuration_checks(app_configs, **kwargs):
    if not settings.WHATSAPP_META_ENABLED:
        return []
    issues = configuration_issues(templates=True)
    expected_senders = {
        "GUEST_CONSULTATION_OTP_SENDER": "apps.whatsapp.meta.send_guest_otp",
        "WHATSAPP_CONSULTATION_NOTIFICATION_SENDER": "apps.whatsapp.meta.send_consultation_notification",
    }
    for key, expected in expected_senders.items():
        if getattr(settings, key) != expected:
            issues.append(key)
    if getattr(settings, "PRODUCTION", False):
        cache_config = settings.CACHES["default"]
        if cache_config["BACKEND"] not in {
            "django.core.cache.backends.redis.RedisCache",
            "django.core.cache.backends.memcached.PyMemcacheCache",
            "django.core.cache.backends.memcached.PyLibMCCache",
        }:
            issues.append("CACHES (shared Redis or Memcached required)")
        options = cache_config.get("OPTIONS", {})
        if options.get("ignore_exc") or options.get("IGNORE_EXCEPTIONS"):
            issues.append("CACHES (cache errors must not be ignored)")
        if not settings.DATABASES["default"]["ENGINE"].endswith("postgresql"):
            issues.append("DATABASES (PostgreSQL required)")
    if not issues:
        return []
    return [
        Error(
            "Meta WhatsApp configuration is incomplete or invalid.",
            hint="Check settings: " + ", ".join(sorted(set(issues))),
            id="whatsapp.E001",
        )
    ]
