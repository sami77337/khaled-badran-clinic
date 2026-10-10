"""Release-scoped URLs for collected public static assets.

Keep the existing non-manifest WhiteNoise backend: the project test suite
renders pages before collectstatic, which deliberately has no manifest.
"""

import os
import re
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from whitenoise.storage import CompressedStaticFilesStorage


_GIT_SHA = re.compile(r"\A[0-9a-fA-F]{40}\Z")


class ReleaseVersionedStaticFilesStorage(CompressedStaticFilesStorage):
    """Refresh browsers' CSS/JS/image URLs when the deployed release changes."""

    def url(self, name):
        url = super().url(name)
        if not getattr(settings, "PRODUCTION", False):
            return url

        revision = os.environ.get("RENDER_GIT_COMMIT", "").strip()
        if not _GIT_SHA.fullmatch(revision):
            # Never put arbitrary environment strings into a public URL.
            return url

        parts = urlsplit(url)
        query = f"{parts.query}&v={revision[:12].lower()}" if parts.query else f"v={revision[:12].lower()}"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
