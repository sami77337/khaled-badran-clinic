"""Accept only browser subscription data, never arbitrary outbound URLs."""
import base64
import math
import re
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec


# Standard browser-operated Web Push transports; no hosted notification SDK.
PUSH_HOSTS = frozenset({
    "fcm.googleapis.com", "web.push.apple.com", "updates.push.services.mozilla.com",
})


def validate_endpoint(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Invalid endpoint.")
    if any(ord(char) <= 32 or ord(char) >= 127 for char in value) or "\\" in value:
        raise ValueError("Invalid endpoint.")
    url = urlsplit(value)
    if (url.scheme != "https" or url.netloc not in PUSH_HOSTS
            or not url.path.startswith("/") or url.path == "/" or url.fragment):
        raise ValueError("Invalid endpoint.")
    return value


def decode_key(value, size):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid key.")
    if len(value) != (size * 8 + 5) // 6:
        raise ValueError("Invalid key.")
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(decoded) != size or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value:
        raise ValueError("Invalid key.")
    return decoded


def validate_subscription(data):
    if not isinstance(data, dict) or set(data) != {"subscription", "language"}:
        raise ValueError("Invalid subscription.")
    if data["language"] not in ("ar", "en"):
        raise ValueError("Invalid language.")
    subscription = data["subscription"]
    if (not isinstance(subscription, dict)
            or not {"endpoint", "keys"} <= subscription.keys()
            or subscription.keys() - {"endpoint", "keys", "expirationTime"}):
        raise ValueError("Invalid subscription.")
    expiry = subscription.get("expirationTime")
    if expiry is not None and (type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry <= 0):
        raise ValueError("Invalid expiry.")
    keys = subscription["keys"]
    if not isinstance(keys, dict) or set(keys) != {"auth", "p256dh"}:
        raise ValueError("Invalid keys.")
    public_key = decode_key(keys["p256dh"], 65)
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_key)
    decode_key(keys["auth"], 16)
    return {
        "endpoint": validate_endpoint(subscription["endpoint"]),
        "p256dh": keys["p256dh"], "auth": keys["auth"], "language": data["language"],
    }
