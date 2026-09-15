from django.test import SimpleTestCase

from apps.core.templatetags.whatsapp_links import whatsapp_bot_url


class WhatsAppBotLinkTests(SimpleTestCase):
    def test_bot_entry_uses_dedicated_number_and_localized_start_message(self):
        self.assertEqual(
            whatsapp_bot_url("ar"),
            "https://wa.me/962798898510?text=%D8%A7%D8%A8%D8%AF%D8%A3",
        )
        self.assertEqual(
            whatsapp_bot_url("en"),
            "https://wa.me/962798898510?text=start",
        )

    def test_unknown_language_falls_back_to_arabic_start(self):
        self.assertEqual(whatsapp_bot_url("fr"), whatsapp_bot_url("ar"))
