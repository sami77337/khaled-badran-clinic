from django.test import SimpleTestCase

from apps.core.templatetags.whatsapp_links import whatsapp_bot_url


class WhatsAppBotLinkTests(SimpleTestCase):
    def test_bot_entry_uses_dedicated_number_without_prefilled_message(self):
        expected = "https://wa.me/962798898510"
        self.assertEqual(whatsapp_bot_url("ar"), expected)
        self.assertEqual(whatsapp_bot_url("en"), expected)

    def test_unknown_language_uses_same_clean_bot_entry(self):
        self.assertEqual(whatsapp_bot_url("fr"), whatsapp_bot_url("ar"))
