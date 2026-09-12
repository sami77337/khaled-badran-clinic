"""Direct, best-effort delivery, only from explicitly scheduled creation events."""
import json
import logging

from cryptography.hazmat.primitives import serialization
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


@sensitive_variables()
def vapid_credentials():
    """Parse environment values in memory; never treat the private key as a path."""
    if not settings.WEB_PUSH_ENABLED:
        return None
    try:
        decode_key(settings.WEB_PUSH_VAPID_PRIVATE_KEY, 32)
        vapid = Vapid.from_raw(settings.WEB_PUSH_VAPID_PRIVATE_KEY.encode("ascii"))
        public = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint,
        )
        if public != decode_key(settings.WEB_PUSH_VAPID_PUBLIC_KEY, 65):
            return None
        subject = settings.WEB_PUSH_VAPID_SUBJECT
        if not isinstance(subject, str) or not subject.startswith("mailto:"):
            return None
        validate_email(subject[7:])
        return vapid
    except Exception:
        return None


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
        vapid = vapid_credentials()
        if vapid is None:
            return
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
                        vapid_claims={"sub": settings.WEB_PUSH_VAPID_SUBJECT},
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
