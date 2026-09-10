import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from . import menu
from .notifications import REPLY_MESSAGES
from .test_meta import META_SETTINGS, SYNTHETIC_PHONE
from .webhook import state_key


@override_settings(**META_SETTINGS)
class MetaWebhookTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("whatsapp_webhook")
        self.send = patch("apps.whatsapp.webhook.meta._send", return_value=True).start()
        self.addCleanup(patch.stopall)

    def message(
        self, message_id="synthetic-event", selection=None, text="Hello", kind="text"
    ):
        message = {
            "id": message_id,
            "from": SYNTHETIC_PHONE.lstrip("+"),
            "timestamp": str(int(time.time())),
            "type": kind,
        }
        if selection is not None:
            message.update(
                type="interactive",
                interactive={
                    "type": "list_reply",
                    "list_reply": {"id": selection, "title": "untrusted-visible-label"},
                },
            )
        elif kind == "text":
            message["text"] = {"body": text}
        else:
            message[kind] = {"id": "private-payload-sentinel"}
        return message

    def envelope(self, messages):
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "202",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "101"},
                                "messages": messages,
                            },
                        }
                    ],
                }
            ],
        }

    def post(self, messages=None, *, payload=None, raw=None, signature=None):
        if raw is None:
            raw = json.dumps(
                payload if payload is not None else self.envelope(messages or []),
                ensure_ascii=False,
            ).encode()
        if signature is None:
            signature = (
                "sha256="
                + hmac.new(b"synthetic-app-secret", raw, hashlib.sha256).hexdigest()
            )
        return self.client.post(
            self.url,
            data=raw,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=signature,
        )

    def test_get_verification_success(self):
        response = self.client.get(
            self.url,
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "synthetic-verify-token",
                "hub.challenge": "synthetic-challenge",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"synthetic-challenge")
        self.send.assert_not_called()

    def test_get_verification_failure(self):
        for token in ("", "wrong", "غير مطابق"):
            response = self.client.get(
                self.url,
                {
                    "hub.mode": "subscribe",
                    "hub.verify_token": token,
                    "hub.challenge": "synthetic-challenge",
                },
            )
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(b"synthetic-challenge", response.content)
        response = self.client.get(
            self.url,
            {
                "hub.mode": "other",
                "hub.verify_token": "synthetic-verify-token",
                "hub.challenge": "value",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_callback_responses_are_never_cacheable(self):
        responses = [
            self.client.get(
                self.url,
                {
                    "hub.mode": "subscribe",
                    "hub.verify_token": "synthetic-verify-token",
                    "hub.challenge": "synthetic-challenge",
                },
            ),
            self.client.get(self.url),
            self.post([self.message()]),
            self.client.delete(self.url),
        ]
        for response in responses:
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertIn("private", response.headers["Cache-Control"])

    def test_valid_raw_hmac_accepts_whitespace_and_arabic(self):
        raw = json.dumps(
            self.envelope([self.message(text="القائمة")]), ensure_ascii=False, indent=2
        ).encode()
        self.assertEqual(self.post(raw=raw).status_code, 200)
        self.send.assert_called_once()

    def test_invalid_missing_and_modified_body_signatures_are_rejected(self):
        raw = json.dumps(self.envelope([self.message()])).encode()
        valid_signature = (
            "sha256="
            + hmac.new(b"synthetic-app-secret", raw, hashlib.sha256).hexdigest()
        )
        for signature in ("", "sha256=" + "0" * 64, "sha1=" + "0" * 64, "invalid"):
            self.assertEqual(self.post(raw=raw, signature=signature).status_code, 403)
        self.assertEqual(
            self.post(raw=raw + b" ", signature=valid_signature).status_code, 403
        )
        self.assertEqual(
            self.client.post(
                self.url, data=raw, content_type="application/json"
            ).status_code,
            403,
        )
        self.send.assert_not_called()

    def test_missing_config_is_unavailable(self):
        for key in (
            "WHATSAPP_META_APP_SECRET",
            "WHATSAPP_META_WABA_ID",
            "WHATSAPP_META_ACCESS_TOKEN",
        ):
            with self.settings(**{key: ""}):
                self.assertEqual(self.post([self.message()]).status_code, 503)
        with self.settings(WHATSAPP_META_VERIFY_TOKEN=""):
            self.assertEqual(self.client.get(self.url).status_code, 503)
        self.send.assert_not_called()

    def test_malformed_or_wrong_account_events_are_rejected(self):
        for payload in (
            [],
            {},
            {"object": "whatsapp_business_account", "entry": [None]},
            self.envelope([None]),
        ):
            self.assertEqual(self.post(payload=payload).status_code, 400)
        for field, value in (("id", "303"),):
            payload = self.envelope([self.message()])
            payload["entry"][0][field] = value
            self.assertEqual(self.post(payload=payload).status_code, 400)
        payload = self.envelope([self.message()])
        payload["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = (
            "303"
        )
        self.assertEqual(self.post(payload=payload).status_code, 400)
        self.assertEqual(self.post(raw=b"invalid-json").status_code, 400)
        self.assertEqual(self.post(raw=b"x" * 262145).status_code, 413)
        self.send.assert_not_called()

    def test_main_list_has_approved_arabic_welcome_and_five_stable_ids(self):
        self.assertEqual(
            self.post([self.message(text="private-payload-sentinel")]).status_code, 200
        )
        phone, content = self.send.call_args.args
        self.assertEqual(phone, SYNTHETIC_PHONE)
        self.assertEqual(content, menu.main_menu("ar"))
        self.assertEqual(
            content["interactive"]["body"]["text"],
            "أهلاً بك في عيادة الدكتور خالد بدران.\nكيف يمكننا مساعدتك؟",
        )
        rows = content["interactive"]["action"]["sections"][0]["rows"]
        self.assertEqual(
            [row["id"] for row in rows],
            ["kbc_book", "kbc_consult", "kbc_portal", "kbc_location", "kbc_staff"],
        )
        self.assertNotIn("private-payload-sentinel", json.dumps(content))

    def test_invalid_timestamps_fail_without_processing_or_private_logs(self):
        for timestamp in (None, True, [], {}, "", "1" * 100, float("inf"), 1.5):
            with self.subTest(timestamp_type=type(timestamp).__name__):
                message = self.message(text="private-payload-sentinel")
                message["timestamp"] = timestamp
                response = self.post([message])
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.content, b"Invalid request")
        self.send.assert_not_called()

    def test_all_ctas_use_existing_routes_and_never_visible_urls(self):
        routes = {
            "kbc_book": "book",
            "kbc_portal": "patient_portal_dashboard",
            "kbc_location": "contact",
            "kbc_consult_registered": "patient_portal_consultation_new",
            "kbc_consult_guest": "guest_consultation_entry",
        }
        for language in ("ar", "en"):
            with self.settings(WHATSAPP_DEFAULT_LANGUAGE=language):
                for selection, route in routes.items():
                    with self.subTest(language=language, selection=selection):
                        self.assertEqual(
                            self.post(
                                [
                                    self.message(
                                        message_id=language + selection,
                                        selection=selection,
                                    )
                                ]
                            ).status_code,
                            200,
                        )
                        content = self.send.call_args.args[1]
                        path = reverse(route + ("_en" if language == "en" else ""))
                        if selection == "kbc_location" and language == "ar":
                            template = content["template"]
                            self.assertEqual(template["name"], "synthetic_location")
                            self.assertEqual(
                                template["components"][0]["parameters"][0]["text"],
                                path.lstrip("/"),
                            )
                            self.assertEqual(
                                menu.DESTINATIONS[selection][1],
                                "افتح الموقع على الخريطة",
                            )
                            continue
                        interactive = content["interactive"]
                        button = interactive["action"]["parameters"]
                        self.assertLessEqual(len(button["display_text"]), 20)
                        self.assertEqual(
                            button["url"], "https://clinic.example.test" + path
                        )
                        self.assertTrue(resolve(path))
                        self.assertNotIn("https://", interactive["body"]["text"])
                        self.assertNotIn("untrusted-visible-label", json.dumps(content))

    def test_consultation_submenu_has_registered_and_guest_reply_buttons(self):
        self.assertEqual(
            self.post([self.message(selection="kbc_consult")]).status_code, 200
        )
        content = self.send.call_args.args[1]
        self.assertEqual(content, menu.consultation_menu("ar"))
        buttons = content["interactive"]["action"]["buttons"]
        self.assertEqual(
            [item["reply"]["id"] for item in buttons],
            ["kbc_consult_registered", "kbc_consult_guest"],
        )
        self.assertEqual(
            [item["reply"]["title"] for item in buttons], ["لدي حساب", "المتابعة كزائر"]
        )
        message = self.message(
            message_id="synthetic-reply-button", selection="kbc_consult_guest"
        )
        message["interactive"] = {
            "type": "button_reply",
            "button_reply": {"id": "kbc_consult_guest", "title": "ignored"},
        }
        self.assertEqual(self.post([message]).status_code, 200)
        self.assertEqual(
            self.send.call_args.args[1],
            menu.destination_message("kbc_consult_guest", "ar"),
        )

    def test_handoff_has_no_followup_bot_loop_and_explicit_menu_resumes(self):
        self.assertEqual(
            self.post([self.message(selection="kbc_staff")]).status_code, 200
        )
        self.assertEqual(
            self.send.call_args.args[1],
            {"type": "text", "text": {"body": menu.HANDOFF["ar"]}},
        )
        self.send.reset_mock()
        for index in range(3):
            self.assertEqual(
                self.post(
                    [
                        self.message(
                            message_id=f"synthetic-followup-{index}",
                            text="private-payload-sentinel",
                        )
                    ]
                ).status_code,
                200,
            )
        self.send.assert_not_called()
        self.assertEqual(
            self.post(
                [self.message(message_id="synthetic-resume", text="القائمة")]
            ).status_code,
            200,
        )
        self.assertEqual(self.send.call_args.args[1], menu.main_menu("ar"))

    def test_handoff_acknowledgement_failure_is_retryable_without_followup_loop(self):
        self.send.return_value = False
        message = self.message(selection="kbc_staff")
        self.assertEqual(self.post([message]).status_code, 503)
        self.send.return_value = True
        self.assertEqual(
            self.post([self.message(message_id="synthetic-followup")]).status_code, 200
        )
        self.assertEqual(self.send.call_count, 1)
        self.assertEqual(self.post([message]).status_code, 200)
        self.assertEqual(self.send.call_count, 2)

    def test_english_selection_persists_only_language_and_handoff_is_localized(self):
        self.assertEqual(self.post([self.message(text="English")]).status_code, 200)
        self.assertEqual(self.send.call_args.args[1], menu.main_menu("en"))
        self.assertEqual(
            self.post(
                [self.message(message_id="synthetic-en-handoff", selection="kbc_staff")]
            ).status_code,
            200,
        )
        self.assertEqual(
            self.send.call_args.args[1]["text"]["body"], menu.HANDOFF["en"]
        )

    def test_duplicate_events_are_sent_once_and_failed_events_can_retry(self):
        message = self.message()
        self.send.return_value = False
        self.assertEqual(self.post([message]).status_code, 503)
        self.send.return_value = True
        self.assertEqual(self.post([message]).status_code, 200)
        self.assertEqual(self.post([message]).status_code, 200)
        self.assertEqual(self.send.call_count, 2)

    def test_busy_conversation_and_cache_failure_fail_closed(self):
        with patch("apps.whatsapp.webhook.cache.add", return_value=False):
            self.assertEqual(self.post([self.message()]).status_code, 503)
        with patch(
            "apps.whatsapp.webhook.cache.get",
            side_effect=RuntimeError("private-payload-sentinel"),
        ):
            with self.assertLogs("apps.whatsapp.webhook", level="WARNING") as logs:
                self.assertEqual(self.post([self.message()]).status_code, 503)
        self.assertNotIn("private-payload-sentinel", " ".join(logs.output))
        self.send.assert_not_called()

    def test_partial_batch_retry_does_not_repeat_successful_messages(self):
        messages = [
            self.message(message_id=f"synthetic-batch-{index}") for index in range(3)
        ]
        self.send.side_effect = [True, False]
        self.assertEqual(self.post(messages).status_code, 503)
        self.assertEqual(self.send.call_count, 2)
        self.send.reset_mock(side_effect=True)
        self.assertEqual(self.post(messages).status_code, 200)
        self.assertEqual(self.send.call_count, 2)
        self.send.reset_mock()
        self.assertEqual(self.post(messages).status_code, 200)
        self.send.assert_not_called()

    def test_media_statuses_and_stale_messages_do_not_trigger_outbound_calls(self):
        for kind in ("image", "video", "audio", "document", "reaction"):
            self.assertEqual(self.post([self.message(kind=kind)]).status_code, 200)
        payload = self.envelope([])
        payload["entry"][0]["changes"][0]["value"]["statuses"] = [
            {"status": "delivered"}
        ]
        self.assertEqual(self.post(payload=payload).status_code, 200)
        message = self.message()
        message["timestamp"] = str(int(time.time()) - 86401)
        self.assertEqual(self.post([message]).status_code, 200)
        self.send.assert_not_called()

    def test_cache_keys_are_keyed_hashes_and_state_has_bounded_ttl(self):
        key = state_key("handoff", SYNTHETIC_PHONE)
        self.assertNotIn(SYNTHETIC_PHONE, key)
        self.assertEqual(len(key.rsplit(":", 1)[1]), 64)
        with patch("apps.whatsapp.webhook.cache.set", wraps=cache.set) as writes:
            self.post([self.message(selection="kbc_staff")])
        for call in writes.call_args_list:
            self.assertGreater(call.kwargs["timeout"], 0)
            self.assertLessEqual(call.kwargs["timeout"], 604800)
            self.assertNotIn(SYNTHETIC_PHONE.lstrip("+"), str(call))

    def test_patient_facing_copy_has_no_forbidden_words_or_media(self):
        for language in ("ar", "en"):
            values = [
                menu.main_menu(language),
                menu.consultation_menu(language),
                menu.HANDOFF[language],
                REPLY_MESSAGES[language],
            ]
            values += [
                menu.destination_message(selection, language)
                for selection in menu.DESTINATIONS
            ]
            copy = json.dumps(values, ensure_ascii=False).casefold()
            for word in ("آمن", "آمنة", "الأمان", "secure", "security"):
                self.assertNotIn(word.casefold(), copy)
            for media in ('"image"', '"video"', '"audio"', '"document"'):
                self.assertNotIn(media, copy)

    def test_csrf_exemption_is_specific_to_the_provider_callback(self):
        self.assertTrue(resolve(self.url).func.csrf_exempt)
        self.assertFalse(
            getattr(
                resolve(reverse("guest_consultation_entry")).func, "csrf_exempt", False
            )
        )
        self.assertEqual(
            self.client.post(reverse("guest_consultation_entry"), {}).status_code, 403
        )
