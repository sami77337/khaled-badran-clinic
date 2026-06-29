"""Development settings for local work."""

import os

from .base import *  # noqa: F403
from .helpers import build_database_config  # noqa: F401


PRODUCTION = False
DEBUG = env_bool("DJANGO_DEBUG", True)  # noqa: F405
ALLOWED_HOSTS = env_list(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS",
    ["localhost", "127.0.0.1", "[::1]"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASES = build_database_config(  # noqa: F405
    DATABASE_URL,
    sqlite_path=BASE_DIR / "db.sqlite3",  # noqa: F405
    conn_max_age=0,
    conn_health_checks=False,
    ssl_require=False,
)
