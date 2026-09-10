"""Narrow Meta Cloud API adapter. No media, arbitrary text or model objects."""

import http.client
import json
import logging
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.urls import resolve
from django.views.decorators.debug import sensitive_variables

from apps.booking.phone import normalize_phone
from .configuration import is_available, website_origin

logger = logging.getLogger(__name__)
HTTP_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 16384


@sensitive_variables()
def _send(phone_e164, content):
    connection = None
    try:
        if not is_available():
            return False
        recipient = normalize_phone(phone_e164).lstrip("+")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            **content,
        }
        # Fixed TLS host, no redirects or retry-on-timeout: acceptance may already
        # have occurred when a connection fails. Never enable HTTP debug output.
        connection = http.client.HTTPSConnection(
            "graph.facebook.com", timeout=HTTP_TIMEOUT_SECONDS
        )
        connection.request(
            "POST",
            f"/{settings.WHATSAPP_META_GRAPH_VERSION}/{settings.WHATSAPP_META_PHONE_NUMBER_ID}/messages",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + settings.WHATSAPP_META_ACCESS_TOKEN,
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise ValueError("Provider did not accept message")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Unexpected provider response")
        result = json.loads(raw)
        messages = result.get("messages") if isinstance(result, dict) else None
        if (
            not isinstance(messages, list)
            or not messages
            or not isinstance(messages[0], dict)
            or not isinstance(messages[0].get("id"), str)
            or not messages[0]["id"]
        ):
            raise ValueError("Provider acceptance missing")
        return True
    except Exception:
        logger.warning("Meta WhatsApp delivery unavailable.")
        return False
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def template_content(kind, language, components):
    name = getattr(settings, f"WHATSAPP_META_{kind}_TEMPLATE", "")
    code = getattr(
        settings,
        "WHATSAPP_META_TEMPLATE_LANGUAGE_EN"
        if language == "en"
        else "WHATSAPP_META_TEMPLATE_LANGUAGE_AR",
        "",
    )
    if not re.fullmatch(r"[a-z0-9_]{1,512}", name) or not re.fullmatch(
        r"[a-z]{2,3}(?:_[A-Z]{2})?", code
    ):
        raise ValueError("WhatsApp template unavailable")
    return {
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": code},
            "components": components,
        },
    }


def _url_button(suffix):
    return {
        "type": "button",
        "sub_type": "url",
        "index": "0",
        "parameters": [{"type": "text", "text": suffix}],
    }


@sensitive_variables()
def send_guest_otp(phone_e164, code, language):
    """Existing OTP contract; Authentication COPY_CODE template, never free text."""
    try:
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
            return False
        return _send(
            phone_e164,
            template_content(
                "OTP",
                language,
                [
                    {"type": "body", "parameters": [{"type": "text", "text": code}]},
                    _url_button(code),
                ],
            ),
        )
    except Exception:
        return False


@sensitive_variables()
def send_consultation_notification(phone_e164, message, website_url, language):
    """Existing reply contract; send only the approved template and route suffix."""
    from .notifications import REPLY_MESSAGES

    try:
        language = "en" if language == "en" else "ar"
        if message != REPLY_MESSAGES[language]:
            return False
        parsed = urlsplit(website_url)
        if (
            parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or website_url != website_origin() + parsed.path
        ):
            return False
        allowed = {"patient_portal_consultation_detail", "guest_consultation_detail"}
        if language == "en":
            allowed = {route + "_en" for route in allowed}
        if resolve(parsed.path).url_name not in allowed:
            return False
        return _send(
            phone_e164,
            template_content(
                "CONSULTATION_REPLY",
                language,
                [
                    _url_button(parsed.path.lstrip("/")),
                ],
            ),
        )
    except Exception:
        return False


@sensitive_variables()
def send_appointment_notification(phone_e164, kind, starts_at, language):
    """Only appointment date/time reaches template parameters; no notes or IDs."""
    from django.utils import timezone

    try:
        if kind not in {"BOOKING_CONFIRMATION", "APPOINTMENT_REMINDER"}:
            return False
        local = timezone.localtime(starts_at)
        return _send(
            phone_e164,
            template_content(
                kind,
                language,
                [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": local.strftime("%Y-%m-%d")},
                            {"type": "text", "text": local.strftime("%H:%M")},
                        ],
                    }
                ],
            ),
        )
    except Exception:
        return False
