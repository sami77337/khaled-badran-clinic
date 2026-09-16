from django.test import SimpleTestCase, override_settings

from . import menu


@override_settings(WHATSAPP_WEBSITE_ORIGIN="https://clinic.example.test")
class PublishedCasesMenuTests(SimpleTestCase):
    def test_arabic_main_menu_exposes_published_cases(self):
        content = menu.main_menu("ar")
        sections = content["interactive"]["action"]["sections"]
        cases_section = sections[2]
        self.assertEqual(cases_section["title"], "الحالات المنشورة")
        self.assertEqual(
            cases_section["rows"],
            [{"id": "kbc_cases", "title": "حالات علاجية منشورة"}],
        )

    def test_english_main_menu_exposes_published_cases(self):
        content = menu.main_menu("en")
        sections = content["interactive"]["action"]["sections"]
        cases_section = sections[2]
        self.assertEqual(cases_section["title"], "Published Cases")
        self.assertEqual(
            cases_section["rows"],
            [{"id": "kbc_cases", "title": "Published Cases"}],
        )

    def test_published_cases_destination_uses_existing_public_cases_routes(self):
        ar = menu.destination_message("kbc_cases", "ar")
        en = menu.destination_message("kbc_cases", "en")
        self.assertEqual(
            ar["interactive"]["action"]["parameters"]["url"],
            "https://clinic.example.test/cases/",
        )
        self.assertEqual(
            en["interactive"]["action"]["parameters"]["url"],
            "https://clinic.example.test/en/cases/",
        )
