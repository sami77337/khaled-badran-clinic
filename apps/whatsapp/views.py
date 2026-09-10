"""Meta WhatsApp webhook verification and inbound routing."""

from __future__ import annotations

import hashlib
import hmac
import json

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt

from apps.core.views import APPROVED_CLINIC_LOCATION
from apps.whatsapp.actions import entry_actions, localized_url
from apps.whatsapp.meta import (
    WhatsAppConfigurationError,
    WhatsAppDeliveryError,
    send_consultation_menu,
    send_cta_url,
    send_main_menu,
    send_text,
    website_url,
)


def _configured_value(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _language() -> str:
    return "en" if getattr(settings, "WHATSAPP_DEFAULT_LANGUAGE", "ar") == "en" else "ar"


def _hashed_cache_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"whatsapp:{prefix}:{digest}"


def _signature_valid(raw_body: bytes, supplied_signature: str) -> bool:
    app_secret = _configured_value("WHATSAPP_META_APP_SECRET")
    if not app_secret or not supplied_signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, supplied_signature)


def _iter_messages(payload):
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry") or ():
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes") or ():
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            if not isinstance(value, dict):
                continue
            for message in value.get("messages") or ():
                if isinstance(message, dict):
                    yield message


def _message_sender(message) -> str:
    sender = str(message.get("from") or "")
    return sender if sender.isdigit() and 7 <= len(sender) <= 20 else ""


def _interactive_reply_id(message) -> str:
    interactive = message.get("interactive") or {}
    if not isinstance(interactive, dict):
        return ""
    for key in ("list_reply", "button_reply"):
        reply = interactive.get(key) or {}
        if isinstance(reply, dict) and reply.get("id"):
            return str(reply["id"])
    return ""


def _action_paths(language: str) -> dict:
    return {item.key: item.url for item in entry_actions(language)}


def _route_interactive(sender: str, reply_id: str, language: str) -> None:
    paths = _action_paths(language)
    if reply_id == "kbc_book":
        send_cta_url(
            sender,
            body="اختر موعدك من موقع العيادة." if language == "ar" else "Choose your appointment on the clinic website.",
            label="احجز موعدك" if language == "ar" else "Book Appointment",
            url=website_url(paths["book"]),
        )
        return
    if reply_id == "kbc_consult":
        send_consultation_menu(sender, language)
        return
    if reply_id == "kbc_consult_registered":
        send_cta_url(
            sender,
            body="يمكنك متابعة الاستشارة من حساب المريض." if language == "ar" else "Continue the consultation from your patient account.",
            label="ابدأ الاستشارة" if language == "ar" else "Start Consultation",
            url=website_url(paths["consult_patient"]),
        )
        return
    if reply_id == "kbc_consult_guest":
        send_cta_url(
            sender,
            body="يمكنك بدء الاستشارة كزائر." if language == "ar" else "You can start the consultation as a guest.",
            label="ابدأ الاستشارة" if language == "ar" else "Start Consultation",
            url=website_url(paths["consult_guest"]),
        )
        return
    if reply_id == "kbc_portal":
        send_cta_url(
            sender,
            body="الدخول إلى حساب المريض." if language == "ar" else "Open your patient account.",
            label="دخول حساب المريض" if language == "ar" else "Patient Login",
            url=website_url(localized_url("patient_portal_login", language)),
        )
        return
    if reply_id == "kbc_location":
        send_cta_url(
            sender,
            body="موقع عيادة الدكتور خالد بدران." if language == "ar" else "Dr. Khaled Badran Clinic location.",
            label="افتح الموقع على الخريطة" if language == "ar" else "Open Map",
            url=APPROVED_CLINIC_LOCATION["map_url"],
        )
        return
    if reply_id == "kbc_staff":
        ttl = int(getattr(settings, "WHATSAPP_META_STAFF_HANDOFF_TTL_SECONDS", 8 * 60 * 60))
        cache.set(_hashed_cache_key("staff-handoff", sender), True, ttl)
        send_text(
            sender,
            "يمكنك كتابة رسالتك هنا وسيقوم فريق العيادة بالرد عليك."
            if language == "ar"
            else "You can write your message here and the clinic team will reply.",
        )
        return
    send_main_menu(sender, language)


def _handle_message(message) -> None:
    sender = _message_sender(message)
    message_id = str(message.get("id") or "")
    if not sender or not message_id:
        return

    dedupe_ttl = int(getattr(settings, "WHATSAPP_META_WEBHOOK_DEDUPE_TTL_SECONDS", 7 * 24 * 60 * 60))
    if not cache.add(_hashed_cache_key("message", message_id), True, dedupe_ttl):
        return

    language = _language()
    handoff_key = _hashed_cache_key("staff-handoff", sender)
    message_type = str(message.get("type") or "")

    if message_type == "interactive":
        _route_interactive(sender, _interactive_reply_id(message), language)
        return

    if message_type == "text":
        body = str((message.get("text") or {}).get("body") or "").strip().casefold()
        if body in {"menu", "start", "القائمة", "ابدأ"}:
            cache.delete(handoff_key)
            send_main_menu(sender, language)
            return
        if cache.get(handoff_key):
            return
        send_main_menu(sender, language)


@csrf_exempt
def meta_webhook(request):
    """Dedicated Meta callback endpoint; no other route is exempted from CSRF."""
    if request.method == "GET":
        verify_token = _configured_value("WHATSAPP_META_VERIFY_TOKEN")
        if not verify_token:
            return HttpResponse("Unavailable", status=503)
        if (
            request.GET.get("hub.mode") == "subscribe"
            and hmac.compare_digest(request.GET.get("hub.verify_token", ""), verify_token)
        ):
            challenge = request.GET.get("hub.challenge", "")
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponseForbidden("Verification failed")

    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    raw_body = request.body
    if not _signature_valid(raw_body, request.headers.get("X-Hub-Signature-256", "")):
        return HttpResponseForbidden("Signature rejected")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponse("Invalid payload", status=400)

    try:
        for message in _iter_messages(payload):
            _handle_message(message)
    except (WhatsAppConfigurationError, WhatsAppDeliveryError, ValueError):
        # The callback itself was authenticated and accepted. Provider-response
        # failures are deliberately not echoed or logged with payload details.
        pass

    return HttpResponse("EVENT_RECEIVED", content_type="text/plain")
