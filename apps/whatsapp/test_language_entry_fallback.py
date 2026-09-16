import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from . import menu
from .test_meta import META_SETTINGS, SYNTHETIC_PHONE
from .webhook import _handle_message, _messages


@override_settings(**META_SETTINGS, WHATSAPP_HANDOFF_TTL_SECONDS=86400)
class WhatsAppLanguageEntryFallbackTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.send = patch("apps.whatsapp.webhook.meta._send", return_value=True).start()
        self.addCleanup(patch.stopall)
        self.sender = SYNTHETIC_PHONE.lstrip("+")

    def payload(self, text, message_id="language-entry-event"):
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": META_SETTINGS["WHATSAPP_META_WABA_ID"],
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "phone_number_id": META_SETTINGS[
                                        "WHATSAPP_META_PHONE_NUMBER_ID"
                                    ]
                                },
                                "messages": [
                                    {
                                        "id": message_id,
                                        "from": self.sender,
                                        "timestamp": str(int(time.time())),
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }

    def test_language_entry_menu_has_only_arabic_and_english(self):
        content = menu.language_entry_menu()
        self.assertEqual(
            content["interactive"]["body"]["text"],
            "اختر اللغة / Choose language",
        )
        buttons = content["interactive"]["action"]["buttons"]
        self.assertEqual(
            [button["reply"]["id"] for button in buttons],
            ["kbc_language_ar", "kbc_language_en"],
        )
        self.assertEqual(
            [button["reply"]["title"] for button in buttons],
            ["العربية", "English"],
        )

    def test_any_unrecognized_text_becomes_language_prompt_without_reflection(self):
        for index, text in enumerate((".", "مرحبا", "Hi there", "حجز موعد")):
            with self.subTest(text=text):
                parsed = _messages(self.payload(text, f"unknown-{index}"))
                self.assertEqual(
                    parsed,
                    [(self.sender, f"unknown-{index}", "kbc_language_prompt", "")],
                )
                self.assertNotIn(text, str(parsed))

    def test_language_prompt_sends_bilingual_choice(self):
        self.assertTrue(
            _handle_message(self.sender, "prompt-event", "kbc_language_prompt", "")
        )
        self.send.assert_called_once_with(SYNTHETIC_PHONE, menu.language_entry_menu())

    def test_language_ice_breakers_open_requested_main_menu(self):
        self.assertTrue(_handle_message(self.sender, "english-event", "", "english"))
        self.send.assert_called_once_with(SYNTHETIC_PHONE, menu.main_menu("en"))
        self.send.reset_mock()
        cache.clear()
        self.assertTrue(_handle_message(self.sender, "arabic-event", "", "العربية"))
        self.send.assert_called_once_with(SYNTHETIC_PHONE, menu.main_menu("ar"))

    def test_staff_handoff_still_suppresses_arbitrary_text_fallback(self):
        self.assertTrue(_handle_message(self.sender, "handoff-event", "kbc_staff", ""))
        self.send.reset_mock()
        self.assertTrue(
            _handle_message(self.sender, "followup-event", "kbc_language_prompt", "")
        )
        self.send.assert_not_called()
