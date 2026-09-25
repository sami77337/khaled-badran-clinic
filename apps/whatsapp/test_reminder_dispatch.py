from collections import Counter
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .test_meta import META_SETTINGS


REMINDER_TOKEN = "synthetic-reminder-cron-token"


@override_settings(**META_SETTINGS, REMINDER_CRON_TOKEN=REMINDER_TOKEN)
class ReminderDispatchEndpointTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("whatsapp_reminder_dispatch")

    def test_endpoint_is_post_only_and_hidden_without_valid_token(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

        with patch("apps.whatsapp.reminder_dispatch.dispatch_due_reminders") as dispatch:
            response = self.client.post(self.url)
            self.assertEqual(response.status_code, 404)
            response = self.client.post(
                self.url,
                HTTP_X_KBC_CRON_TOKEN="wrong-token",
            )
            self.assertEqual(response.status_code, 404)
        dispatch.assert_not_called()

    def test_authorized_post_dispatches_without_csrf_cookie(self):
        with (
            patch.object(
                __import__(
                    "apps.whatsapp.reminder_dispatch",
                    fromlist=["connection"],
                ).connection.features,
                "has_select_for_update",
                True,
            ),
            patch(
                "apps.whatsapp.reminder_dispatch.dispatch_due_reminders",
                return_value=Counter(sent=2, skipped=1, failed=0),
            ) as dispatch,
        ):
            response = self.client.post(
                self.url,
                HTTP_X_KBC_CRON_TOKEN=REMINDER_TOKEN,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "sent": 2, "skipped": 1, "failed": 0},
        )
        dispatch.assert_called_once_with(limit=20)

    def test_failed_dispatch_returns_503_with_counts_only(self):
        with (
            patch.object(
                __import__(
                    "apps.whatsapp.reminder_dispatch",
                    fromlist=["connection"],
                ).connection.features,
                "has_select_for_update",
                True,
            ),
            patch(
                "apps.whatsapp.reminder_dispatch.dispatch_due_reminders",
                return_value=Counter(sent=1, skipped=0, failed=1),
            ),
        ):
            response = self.client.post(
                self.url,
                HTTP_X_KBC_CRON_TOKEN=REMINDER_TOKEN,
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"ok": False, "sent": 1, "skipped": 0, "failed": 1},
        )
        self.assertNotContains(response, "patient", status_code=503)
        self.assertNotContains(response, "phone", status_code=503)

    @override_settings(REMINDER_CRON_TOKEN="")
    def test_missing_server_token_fails_closed(self):
        with patch("apps.whatsapp.reminder_dispatch.dispatch_due_reminders") as dispatch:
            response = self.client.post(
                self.url,
                HTTP_X_KBC_CRON_TOKEN=REMINDER_TOKEN,
            )

        self.assertEqual(response.status_code, 404)
        dispatch.assert_not_called()
