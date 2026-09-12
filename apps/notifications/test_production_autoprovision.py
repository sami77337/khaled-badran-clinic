import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .services import _auto_provision_allowed, vapid_credentials


class ProductionVapidAutoProvisionTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="push-auto-staff",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_explicit_disabled_flag_wins_over_production_auto_provision(self):
        with override_settings(
            PRODUCTION=True,
            PRIVATE_MEDIA_ROOT=Path("/var/data/private"),
            WEB_PUSH_ENABLED=False,
            WEB_PUSH_VAPID_PUBLIC_KEY="",
            WEB_PUSH_VAPID_PRIVATE_KEY="",
            WEB_PUSH_VAPID_SUBJECT="",
        ), patch.dict(os.environ, {"WEB_PUSH_ENABLED": "false"}, clear=False):
            self.assertFalse(_auto_provision_allowed())
            self.assertIsNone(vapid_credentials())

    def test_auto_provision_persists_private_key_and_exposes_only_public_key(self):
        with TemporaryDirectory() as tempdir:
            private_root = Path(tempdir) / "private"
            with override_settings(
                PRODUCTION=True,
                PRIVATE_MEDIA_ROOT=private_root,
                WEB_PUSH_ENABLED=False,
                WEB_PUSH_VAPID_PUBLIC_KEY="",
                WEB_PUSH_VAPID_PRIVATE_KEY="",
                WEB_PUSH_VAPID_SUBJECT="",
            ), patch.dict(os.environ, {"WEB_PUSH_ENABLED": ""}, clear=False), patch(
                "apps.notifications.services._auto_provision_allowed",
                return_value=True,
            ):
                first = self.client.get(reverse("staff_push_config"))
                second = self.client.get(reverse("staff_push_config"))

            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            first_payload = first.json()
            second_payload = second.json()
            self.assertTrue(first_payload["available"])
            self.assertEqual(first_payload, second_payload)
            self.assertEqual(len(first_payload["publicKey"]), 87)

            key_path = private_root.parent / "webpush" / "vapid-private.key"
            self.assertTrue(key_path.exists())
            self.assertEqual(stat.S_IMODE(key_path.stat().st_mode), 0o600)
            private_key = key_path.read_text(encoding="ascii").strip()
            self.assertEqual(len(private_key), 43)
            self.assertNotIn(private_key, first.content.decode("utf-8"))
