"""Small, testable helpers for environment-driven Django settings."""

from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def parse_bool(value, default=False):
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def env_bool(name, default=False):
    import os

    return parse_bool(os.getenv(name), default=default)


def parse_list(value, default=None):
    if value is None or str(value).strip() == "":
        return list(default or [])
    return [item.strip() for item in str(value).split(",") if item.strip()]


def env_list(name, default=None):
    import os

    return parse_list(os.getenv(name), default=default)


def parse_int(value, default, minimum=None, maximum=None):
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    if maximum is not None and parsed > maximum:
        return maximum
    return parsed


def env_int(name, default, minimum=None, maximum=None):
    import os

    return parse_int(os.getenv(name), default, minimum=minimum, maximum=maximum)


def build_database_config(
    database_url,
    *,
    sqlite_path,
    conn_max_age=0,
    conn_health_checks=False,
    ssl_require=False,
):
    """Return a Django DATABASES dict.

    SQLite fallback is for local development and CI only. Production settings
    should pass an explicit DATABASE_URL and deployment checks reject SQLite
    when production mode is enabled.
    """

    if database_url:
        return {
            "default": dj_database_url.parse(
                database_url,
                conn_max_age=conn_max_age,
                conn_health_checks=conn_health_checks,
                ssl_require=ssl_require,
            )
        }

    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(sqlite_path),
        }
    }


def build_cache_config(cache_url, *, key_prefix="kbc"):
    """Return a Django CACHES dict from CACHE_URL.

    Empty CACHE_URL intentionally uses LocMemCache for local development. Use a
    shared backend such as Redis in production so rate limits work across
    processes and hosts.
    """

    if not cache_url:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "khaled-badran-clinic-local",
                "KEY_PREFIX": key_prefix,
            }
        }

    parsed = urlparse(cache_url)
    scheme = parsed.scheme.lower()

    if scheme in {"redis", "rediss"}:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": cache_url,
                "KEY_PREFIX": key_prefix,
            }
        }

    if scheme == "locmem":
        location = (parsed.netloc + parsed.path).strip("/") or "khaled-badran-clinic-local"
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": location,
                "KEY_PREFIX": key_prefix,
            }
        }

    raise ImproperlyConfigured(
        "CACHE_URL must be empty, locmem://<name>, redis://..., or rediss://..."
    )


def secure_proxy_ssl_header(enabled):
    if enabled:
        return ("HTTP_X_FORWARDED_PROTO", "https")
    return None
