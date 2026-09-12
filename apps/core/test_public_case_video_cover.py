from django.test import TestCase
from django.urls import reverse

from apps.records.models import PublicCase, PublicCaseMedia

from .showcase import grouped_public_cases
from .tests import PublicCasesTestDataMixin


class PublicCaseVideoCoverTests(PublicCasesTestDataMixin, TestCase):
    def create_video(self, case, **kwargs):
        return self.create_public_media(
            public_case=case,
            role=PublicCaseMedia.Role.VIDEO,
            media_type=PublicCaseMedia.MediaType.SHORT_VIDEO,
            **kwargs,
        )

    def create_cover(self, case, **kwargs):
        return self.create_public_media(
            public_case=case, role=PublicCaseMedia.Role.VIDEO_COVER, **kwargs
        )

    def assert_cover_unavailable(self, cover):
        cover.refresh_from_db()
        self.assertFalse(cover.is_publicly_available)
        for language in ("ar", "en"):
            suffix = "_en" if language == "en" else ""
            url = reverse(f"public_case_media{suffix}", args=[cover.public_id])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertNotIn(url, str(grouped_public_cases(language)))

    def test_cover_is_video_poster_on_home_list_and_detail_in_both_languages(self):
        case = self.create_public_case()
        video = self.create_video(case)
        cover = self.create_cover(case)

        self.assertTrue(cover.is_publicly_available)
        for language in ("ar", "en"):
            with self.subTest(language=language):
                suffix = "_en" if language == "en" else ""
                url = reverse(f"public_case_media{suffix}", args=[cover.public_id])
                group = grouped_public_cases(language)[0]
                self.assertEqual(group["video_items"][0]["poster_url"], url)
                self.assertEqual(group["teaser"]["poster_url"], url)
                for key in ("items", "carousel_items"):
                    self.assertEqual([item["public_id"] for item in group[key]], [video.public_id])
                routes = (
                    reverse(f"home{suffix}"),
                    reverse(f"public_cases{suffix}"),
                    reverse(f"public_case_detail{suffix}", args=[case.pk]),
                )
                for route in routes:
                    response = self.client.get(route)
                    self.assertEqual(response.status_code, 200)
                    self.assertRegex(response.content.decode(), rf'<video\b[^>]*poster="{url}"')
                    self.assertNotContains(response, cover.file.name)
                    self.assertNotContains(response, cover.original_filename)
                response = self.client.get(url)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response["Content-Type"], "image/jpeg")
                    self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                    self.assertIn("no-store", response["Cache-Control"])
                    self.assertNotIn(cover.original_filename, response["Content-Disposition"])
                    self.assertEqual(b"".join(response.streaming_content), b"public-image-bytes")
                finally:
                    response.close()

    def test_latest_eligible_cover_applies_to_each_video_only_in_its_own_case(self):
        case = self.create_public_case()
        self.create_video(case)
        self.create_video(case)
        self.create_cover(case)
        cover = self.create_cover(case)
        self.create_cover(case, consent_confirmed=False)
        other_case = self.create_public_case()
        self.create_video(other_case)

        with self.assertNumQueries(1):
            groups = {group["case_id"]: group for group in grouped_public_cases("en")}
        expected = reverse("public_case_media_en", args=[cover.public_id])
        self.assertEqual([item["poster_url"] for item in groups[case.pk]["video_items"]], [expected] * 2)
        self.assertEqual(groups[other_case.pk]["video_items"][0]["poster_url"], "")

    def test_ineligible_covers_are_neither_posters_nor_publicly_served(self):
        for mutation in ("consent", "inactive", "missing", "empty", "wrong_type"):
            with self.subTest(mutation=mutation):
                case = self.create_public_case()
                self.create_video(case)
                cover = self.create_cover(case)
                if mutation == "missing":
                    cover.file.storage.delete(cover.file.name)
                else:
                    updates = {
                        "consent": {"consent_confirmed": False},
                        "inactive": {"is_active": False},
                        "empty": {"file": ""},
                        "wrong_type": {"media_type": PublicCaseMedia.MediaType.SHORT_VIDEO},
                    }
                    PublicCaseMedia.objects.filter(pk=cover.pk).update(**updates[mutation])
                self.assert_cover_unavailable(cover)
                group = grouped_public_cases("en", case_id=case.pk)[0]
                self.assertEqual(group["video_items"][0]["poster_url"], "")

    def test_cover_requires_eligible_video_in_same_case_even_with_public_image(self):
        for mutation in ("consent", "inactive", "missing", "empty", "invalid_role", "image", "deleted"):
            with self.subTest(mutation=mutation):
                case = self.create_public_case()
                self.create_public_media(public_case=case)
                video = self.create_video(case)
                cover = self.create_cover(case)
                self.assertTrue(cover.is_publicly_available)
                if mutation == "missing":
                    video.file.storage.delete(video.file.name)
                elif mutation == "deleted":
                    video.delete()
                else:
                    updates = {
                        "consent": {"consent_confirmed": False},
                        "inactive": {"is_active": False},
                        "empty": {"file": ""},
                        "invalid_role": {"role": ""},
                        "image": {"media_type": PublicCaseMedia.MediaType.IMAGE},
                    }
                    PublicCaseMedia.objects.filter(pk=video.pk).update(**updates[mutation])
                case.refresh_from_db()
                self.assertTrue(case.is_published)
                self.assert_cover_unavailable(cover)

    def test_cover_requires_case_consent_and_publication(self):
        for field in ("consent_confirmed", "is_published"):
            with self.subTest(field=field):
                case = self.create_public_case()
                self.create_video(case)
                cover = self.create_cover(case)
                PublicCase.objects.filter(pk=case.pk).update(**{field: False})
                self.assert_cover_unavailable(cover)
                self.assertEqual(grouped_public_cases("en", case_id=case.pk), [])

    def test_cover_only_cannot_publish_or_keep_case_published(self):
        case = self.create_public_case()
        video = self.create_video(case)
        cover = self.create_cover(case)
        video.delete()
        case.refresh_from_db()
        self.assertFalse(case.is_published)
        self.assertFalse(case.has_publishable_media())
        # Even an inconsistent publication flag must not expose a cover-only case.
        PublicCase.objects.filter(pk=case.pk).update(is_published=True)
        self.assertEqual(grouped_public_cases("en"), [])
        self.assert_cover_unavailable(cover)
