"""Drop callback access-log records: verification credentials live in the query."""

import logging


class WebhookPrivacyFilter(logging.Filter):
    def filter(self, record):
        request = getattr(record, "request", None)
        if getattr(request, "path", "") == "/integrations/whatsapp/webhook/":
            return False
        return "/integrations/whatsapp/webhook/" not in record.getMessage()
