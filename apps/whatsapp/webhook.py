"""Authenticated Meta callbacks; no message bodies, media or contact records saved."""

import hashlib
import hmac
import json
import logging
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_http_methods

from . import menu, meta
from .configuration import is_available

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 262144
RECEIPT_TTL = 7 * 24 * 60 * 60
LOCK_TTL = 60


def state_key(purpose, identifier):
    digest = salted_hmac(
        "whatsapp." + purpose, identifier, algorithm="sha256"
    ).hexdigest()
    return "whatsapp:" + purpose + ":" + digest


def _messages(payload):
    if (
        not isinstance(payload, dict)
        or payload.get("object") != "whatsapp_business_account"
    ):
        raise ValueError("Unexpected event")
    entries = payload.get("entry")
    if not isinstance(entries, list) or len(entries) > 50:
        raise ValueError("Unexpected entries")
    messages = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or entry.get("id") != settings.WHATSAPP_META_WABA_ID
        ):
            raise ValueError("Unexpected account")
        changes = entry.get("changes")
        if not isinstance(changes, list) or len(changes) > 50:
            raise ValueError("Unexpected changes")
        for change in changes:
            if not isinstance(change, dict):
                raise ValueError("Unexpected change")
            if change.get("field") != "messages":
                continue
            value = change.get("value")
            if (
                not isinstance(value, dict)
                or value.get("messaging_product") != "whatsapp"
                or not isinstance(value.get("metadata"), dict)
                or value["metadata"].get("phone_number_id")
                != settings.WHATSAPP_META_PHONE_NUMBER_ID
            ):
                raise ValueError("Unexpected destination")
            items = value.get("messages", [])
            if not isinstance(items, list):
                raise ValueError("Unexpected messages")
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Unexpected message")
                # Delivery statuses, echoes, reactions and unsolicited media do
                # not trigger responses. Never fetch attachments or copy text.
                if item.get("type") not in {"text", "interactive"}:
                    continue
                sender, message_id = item.get("from"), item.get("id")
                if (
                    not isinstance(sender, str)
                    or not re.fullmatch(r"[1-9][0-9]{7,14}", sender)
                    or not isinstance(message_id, str)
                    or not 1 <= len(message_id) <= 512
                ):
                    raise ValueError("Unexpected message identity")
                timestamp = item.get("timestamp")
                if (
                    not isinstance(timestamp, (str, int))
                    or isinstance(timestamp, bool)
                    or not re.fullmatch(r"[0-9]{1,12}", str(timestamp))
                ):
                    raise ValueError("Unexpected timestamp")
                timestamp = int(timestamp)
                # Interactive messages are replies within the customer-service
                # window. Ignore late retries outside that window.
                if timestamp < time.time() - 86400 or timestamp > time.time() + 300:
                    continue
                selection, command = "", ""
                if item["type"] == "interactive":
                    interactive = item.get("interactive")
                    if not isinstance(interactive, dict):
                        raise ValueError("Unexpected interactive message")
                    reply_type = interactive.get("type")
                    if reply_type not in {"list_reply", "button_reply"}:
                        continue
                    reply = interactive.get(reply_type)
                    if not isinstance(reply, dict) or not isinstance(
                        reply.get("id"), str
                    ):
                        raise ValueError("Unexpected reply")
                    selection = reply["id"]
                else:
                    text = item.get("text")
                    if not isinstance(text, dict) or not isinstance(
                        text.get("body"), str
                    ):
                        raise ValueError("Unexpected text")
                    # Only these literal control words leave the parser; all
                    # other patient-written text is discarded, never echoed.
                    candidate = text["body"].strip().casefold()
                    if candidate in {
                        "menu",
                        "start",
                        "القائمة",
                        "ابدأ",
                        "english",
                        "العربية",
                    }:
                        command = candidate
                messages.append((sender, message_id, selection, command))
                if len(messages) > 50:
                    raise ValueError("Too many messages")
    return messages


@sensitive_variables()
def _handle_message(sender, message_id, selection, command):
    identity = settings.WHATSAPP_META_PHONE_NUMBER_ID + ":" + sender
    receipt = state_key("receipt", identity + ":" + message_id)
    lock = state_key("conversation-lock", identity)
    if cache.get(receipt):
        return True
    if not cache.add(lock, True, timeout=LOCK_TTL):
        return False  # Retry instead of acknowledging work still in flight.
    try:
        if cache.get(receipt):
            return True
        handoff_key = state_key("handoff", identity)
        language_key = state_key("language", identity)
        language = cache.get(language_key) or settings.WHATSAPP_DEFAULT_LANGUAGE
        language = "en" if language == "en" else "ar"
        if command in {"english", "العربية"}:
            language = "en" if command == "english" else "ar"
            cache.set(language_key, language, timeout=86400)
        if command:
            cache.delete(handoff_key)  # Explicit menu/language request resumes the bot.
        handoff = cache.get(handoff_key)
        if handoff and handoff != receipt:
            accepted = True  # Clinic staff handle follow-ups; no bot response.
        elif selection == "kbc_staff":
            # Set suppression before the HTTP call, retaining it on failure.
            # A retry of this same event can still deliver the acknowledgement.
            cache.set(
                handoff_key, receipt, timeout=settings.WHATSAPP_HANDOFF_TTL_SECONDS
            )
            accepted = meta._send(
                "+" + sender, {"type": "text", "text": {"body": menu.HANDOFF[language]}}
            )
        elif selection == "kbc_consult":
            accepted = meta._send("+" + sender, menu.consultation_menu(language))
        elif selection in menu.DESTINATIONS:
            accepted = meta._send(
                "+" + sender, menu.destination_message(selection, language)
            )
        else:
            accepted = meta._send("+" + sender, menu.main_menu(language))
        if accepted:
            cache.set(receipt, True, timeout=RECEIPT_TTL)
        return accepted
    finally:
        cache.delete(lock)


@csrf_exempt
@never_cache
@require_http_methods(["GET", "POST"])
@sensitive_variables()
def webhook(request):
    if request.method == "GET":
        verify_token = settings.WHATSAPP_META_VERIFY_TOKEN
        if not settings.WHATSAPP_META_ENABLED or not verify_token:
            return HttpResponse("Unavailable", status=503)
        supplied = request.GET.get("hub.verify_token", "")
        challenge = request.GET.get("hub.challenge", "")
        if (
            request.GET.get("hub.mode") != "subscribe"
            or not challenge
            or len(challenge) > 512
            or not hmac.compare_digest(
                supplied.encode("utf-8"), verify_token.encode("utf-8")
            )
        ):
            return HttpResponse("Forbidden", status=403)
        return HttpResponse(challenge, content_type="text/plain")

    if not is_available():
        return HttpResponse("Unavailable", status=503)
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not re.fullmatch(r"sha256=[a-fA-F0-9]{64}", signature):
        return HttpResponse("Forbidden", status=403)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BODY_BYTES:
            return HttpResponse("Request too large", status=413)
        raw = request.body
        if len(raw) > MAX_BODY_BYTES:
            return HttpResponse("Request too large", status=413)
        expected = hmac.new(
            settings.WHATSAPP_META_APP_SECRET.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature[7:].lower()):
            return HttpResponse("Forbidden", status=403)
        messages = _messages(json.loads(raw))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return HttpResponse("Invalid request", status=400)
    deadline = time.monotonic() + 20
    try:
        for message in messages:
            if time.monotonic() >= deadline or not _handle_message(*message):
                return HttpResponse("Unavailable", status=503)
    except Exception:
        logger.warning("WhatsApp callback processing unavailable.")
        return HttpResponse("Unavailable", status=503)
    return JsonResponse({"status": "ok"})
