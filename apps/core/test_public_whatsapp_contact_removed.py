from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class PublicWhatsAppContactRemovalTests(TestCase):
    def test_public_home_and_contact_pages_do_not_offer_whatsapp_chat(self):
        for route_name in ("home", "home_en", "contact", "contact_en"):
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "https://wa.me/")
                self.assertNotContains(response, 'class="whatsapp-quick-link"')
                self.assertNotContains(response, "واتساب العيادة")
                self.assertNotContains(response, "Clinic WhatsApp")

    def test_booking_success_template_has_no_public_whatsapp_action(self):
        source = (
            Path(settings.BASE_DIR) / "templates" / "booking" / "success.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("whatsapp_url", source)
        self.assertNotIn("واتساب العيادة", source)
        self.assertNotIn("Clinic WhatsApp", source)

    def test_public_shell_templates_have_no_direct_whatsapp_contact_links(self):
        for relative_path in (
            "templates/base.html",
            "templates/partials/footer.html",
            "templates/core/contact.html",
        ):
            with self.subTest(path=relative_path):
                source = (Path(settings.BASE_DIR) / relative_path).read_text(
                    encoding="utf-8"
                )
                self.assertNotIn('href="{{ whatsapp_url }}"', source)
                self.assertNotIn("whatsapp_bot_url", source)

    def test_whatsapp_policy_describes_operational_use_not_public_chat(self):
        arabic = self.client.get(reverse("whatsapp_policy"))
        english = self.client.get(reverse("whatsapp_policy_en"))

        self.assertContains(
            arabic,
            "لا يوفّر الموقع قناة محادثة عامة مع العيادة عبر واتساب",
        )
        self.assertContains(
            english,
            "The website does not provide a public WhatsApp chat channel with the clinic.",
        )
        self.assertNotContains(arabic, "لا توجد WhatsApp Business API")
        self.assertNotContains(english, "There is no WhatsApp Business API")

    def test_footer_emergency_copy_no_longer_mentions_public_whatsapp(self):
        arabic = self.client.get(reverse("home"))
        english = self.client.get(reverse("home_en"))

        self.assertContains(arabic, "الموقع ليس للطوارئ")
        self.assertContains(english, "The website is not for emergencies.")
        self.assertNotContains(arabic, "الموقع وواتساب ليسا للطوارئ")
        self.assertNotContains(english, "The website and WhatsApp are not for emergencies.")
