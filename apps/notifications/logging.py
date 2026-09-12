"""Keep delivery credentials out of SQL and transport debug/error logs."""
from contextvars import ContextVar
import logging


push_delivery_in_progress = ContextVar("push_delivery_in_progress", default=False)


class PushPrivacyFilter(logging.Filter):
    def filter(self, record):
        if push_delivery_in_progress.get():
            return False
        # SQL debug records can include the subscription keys as parameters.
        if record.name.startswith("django.db.backends"):
            return "notifications_staffpushsubscription" not in record.getMessage().lower()
        # Do not include request/locals in error reports for the JSON API.
        request = getattr(record, "request", None)
        return not getattr(request, "path", "").startswith("/dashboard/phone-notifications/")
