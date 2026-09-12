from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class HomeCaseGalleryMarkupTests(SimpleTestCase):
    def test_home_cases_use_interactive_gallery_without_detail_page_links(self):
        template = (Path(settings.BASE_DIR) / "templates/core/home.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("case.carousel_items", template)
        self.assertIn("data-case-album", template)
        self.assertIn("data-case-prev", template)
        self.assertIn("data-case-next", template)
        self.assertIn("data-case-expand", template)
        self.assertIn('include "partials/public_case_lightbox.html"', template)
        self.assertNotIn('href="{{ case.detail_url }}"', template)
        self.assertNotIn("home-case-detail-link", template)

    def test_home_case_lightbox_exposes_required_controls(self):
        partial = (
            Path(settings.BASE_DIR) / "templates/partials/public_case_lightbox.html"
        ).read_text(encoding="utf-8")

        self.assertIn("data-case-lightbox", partial)
        self.assertIn("data-lightbox-close", partial)
        self.assertIn("data-lightbox-prev", partial)
        self.assertIn("data-lightbox-next", partial)
        self.assertIn("data-lightbox-media", partial)
