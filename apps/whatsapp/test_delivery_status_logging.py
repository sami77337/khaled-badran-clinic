from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .test_meta import META_SETTINGS, SYNTHETIC_PHONE
from .webhook import _messages


@override_settings(**META_SETTINGS)
class DeliveryStatusLoggingTests(SimpleTestCase):
    def payload(self, *, status, errors=None):
        item = {
            "id": "wamid.synthetic-private-message-id",
            "recipient_id": SYNTHETIC_PHONE.lstrip("+"),
            "status": status,
            "timestamp": "1",
        }
        if errors is not None:
            item["errors"] = errors
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "202",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "101"},
                                "statuses": [item],
                            },
                        }
                    ],
                }
            ],
        }

    def test_failed_status_logs_only_status_and_numeric_error_codes(self):
        payload = self.payload(
            status="failed",
            errors=[
                {
                    "code": 131026,
                    "title": "private-title-sentinel",
                    "message": "private-message-sentinel",
                    "error_data": {"details": "private-details-sentinel"},
                }
            ],
        )
        with patch("apps.whatsapp.webhook.logger.info") as log:
            self.assertEqual(_messages(payload), [])

        log.assert_called_once_with(
            "WhatsApp delivery status=%s error_codes=%s",
            "failed",
            "131026",
        )
        rendered = " ".join(str(value) for value in log.call_args.args)
        self.assertNotIn(SYNTHETIC_PHONE.lstrip("+"), rendered)
        self.assertNotIn("wamid.synthetic-private-message-id", rendered)
        self.assertNotIn("private-title-sentinel", rendered)
        self.assertNotIn("private-message-sentinel", rendered)
        self.assertNotIn("private-details-sentinel", rendered)

    def test_success_status_logs_without_recipient_or_message_identity(self):
        payload = self.payload(status="delivered")
        with patch("apps.whatsapp.webhook.logger.info") as log:
            self.assertEqual(_messages(payload), [])

        log.assert_called_once_with(
            "WhatsApp delivery status=%s error_codes=%s",
            "delivered",
            "none",
        )
        rendered = " ".join(str(value) for value in log.call_args.args)
        self.assertNotIn(SYNTHETIC_PHONE.lstrip("+"), rendered)
        self.assertNotIn("wamid.synthetic-private-message-id", rendered)
