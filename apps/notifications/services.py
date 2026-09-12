"""Direct, best-effort delivery, only from explicitly scheduled creation events."""
import base64
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.validators import validate_email
from django.db import transaction
from django.views.decorators.debug import sensitive_variables
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from requests import Session

from .logging import push_delivery_in_progress
from .models import StaffPushSubscription
from .validation import decode_key, validate_endpoint


logger = logging.getLogger(__name__)
EVENT_TAGS = {
    "new-consultation": "kbc-new-consultation",
    "new-booking": "kbc-new-booking",
}
AUTO_VAPID_SUBJECT = "https://drkhaledbadran.com"


def _encode_key(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _auto_provision_allowed():
    """Auto-provision only on production when private media is on the Render persistent disk."""
    explicit_enabled = os.getenv("WEB_PUSH_ENABLED")
    if explicit_enabled is not None and explicit_enabled.strip():
        return False
    if not settings.PRODUCTION:
        return False
    try:
        Path(settings.PRIVATE_MEDIA_ROOT).relative_to(Path("/var/data"))
    except (TypeError, ValueError):
        return False
    return True


def _web_push_enabled():
    if settings.WEB_PUSH_ENABLED:
        return True
    explicit_enabled = os.getenv("WEB_PUSH_ENABLED")
    if explicit_enabled is not None and explicit_enabled.strip():
        return False
    return _auto_provision_allowed()


def _auto_private_key_path():
    return Path(settings.PRIVATE_MEDIA_ROOT).parent / "webpush" / "vapid-private.key"


def _load_or_create_auto_private_key():
    path = _auto_private_key_path()
    try:
        return path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        pass

    path.parent.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    encoded = _encode_key(key.private_numbers().private_value.to_bytes(32, "big"))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text(encoding="ascii").strip()
    try:
        os.write(fd, encoded.encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return encoded


def _resolved_subject(auto_provision):
    subject = str(settings.WEB_PUSH_VAPID_SUBJECT or "").strip()
    if not subject and auto_provision:
        subject = AUTO_VAPID_SUBJECT
    if subject.startswith("mailto:"):
        validate_email(subject[7:])
        return subject
    parsed = urlsplit(subject)
    if (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
    ):
        return subject
    raise ValueError("Invalid VAPID subject.")


@sensitive_variables()
def _resolved_vapid_configuration():
    if not _web_push_enabled():
        return None
    auto_provision = _auto_provision_allowed()
    try:
        configured_private = str(settings.WEB_PUSH_VAPID_PRIVATE_KEY or "").strip()
        configured_public = str(settings.WEB_PUSH_VAPID_PUBLIC_KEY or "").strip()
        if configured_private or configured_public:
            if not configured_private or not configured_public:
                return None
            private_key = configured_private
        elif auto_provision:
            private_key = _load_or_create_auto_private_key()
        else:
            return None

        decode_key(private_key, 32)
        vapid = Vapid.from_raw(private_key.encode("ascii"))
        public_bytes = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        if configured_public:
            if public_bytes != decode_key(configured_public, 65):
                return None
            public_key = configured_public
        else:
            public_key = _encode_key(public_bytes)
        subject = _resolved_subject(auto_provision)
        return vapid, public_key, subject
    except Exception:
        return None


@sensitive_variables()
def vapid_credentials():
    """Return valid VAPID credentials without exposing private key material."""
    configuration = _resolved_vapid_configuration()
    return configuration[0] if configuration is not None else None


def vapid_public_key():
    configuration = _resolved_vapid_configuration()
    return configuration[1] if configuration is not None else ""


class PushSession(Session):
    def request(self, method, url, **kwargs):
        validate_endpoint(url)
        # Never forward subscription credentials to a redirect destination.
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


def event_payload(event, language):
    if event not in EVENT_TAGS or language not in ("ar", "en"):
        raise ValueError("Unsupported push event.")
    # There is intentionally no model, text, identifier or URL argument here.
    return {"event": event, "language": language}


@sensitive_variables()
def deliver_staff_event(event):
    """Do not let provider/configuration/database errors escape into creation."""
    token = push_delivery_in_progress.set(True)
    try:
        configuration = _resolved_vapid_configuration()
        if configuration is None:
            return
        vapid, _public_key, subject = configuration
        tag = EVENT_TAGS[event]
        subscriptions = StaffPushSubscription.objects.filter(user__is_active=True, user__is_staff=True)
        with PushSession() as session:
            for subscription in subscriptions.iterator():
                try:
                    validate_endpoint(subscription.endpoint)
                    webpush(
                        subscription_info={"endpoint": subscription.endpoint, "keys": {
                            "p256dh": subscription.p256dh, "auth": subscription.auth,
                        }},
                        data=json.dumps(event_payload(event, subscription.language)),
                        vapid_private_key=vapid,
                        # pywebpush mutates claims: use a fresh mapping per device.
                        vapid_claims={"sub": subject},
                        content_encoding="aes128gcm", ttl=3600, timeout=3,
                        headers={"Topic": tag, "Urgency": "normal"},
                        requests_session=session,
                    )
                except WebPushException as error:
                    if error.response is not None and error.response.status_code in (404, 410):
                        # Do not delete a subscription refreshed during the send.
                        StaffPushSubscription.objects.filter(
                            pk=subscription.pk, updated_at=subscription.updated_at,
                        ).delete()
                except Exception:
                    # Continue to the other devices. Never stringify an exception.
                    continue
    except Exception:
        # Also contains iteration, configuration and stale-cleanup failures.
        pass
    finally:
        push_delivery_in_progress.reset(token)


def schedule_staff_event(event):
    if event not in EVENT_TAGS:
        raise ValueError("Unsupported push event.")

    def after_commit():
        try:
            deliver_staff_event(event)
        except Exception:
            # Defensive boundary: no exception details, identifiers or payloads.
            logger.warning("Staff phone notification delivery unavailable.")

    transaction.on_commit(after_commit)
