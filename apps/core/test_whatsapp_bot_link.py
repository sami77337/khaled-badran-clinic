from django.test import SimpleTestCase

from apps.core.templatetags.whatsapp_links import whatsapp_bot_url


class WhatsAppBotLinkTests(SimpleTestCase):
    def test_bot_entry_uses_dedicated_number_without_prefilled_text(self):
        expected = "https://wa.me/962798898510"
        self.assertEqual(whatsapp_bot_url("ar"), expected)
        self.assertEqual(whatsapp_bot_url("en"), expected)
        self.assertEqual(whatsapp_bot_url("fr"), expected)
        self.assertNotIn("?text=", expected)
