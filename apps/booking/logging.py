"""Redact bearer reschedule links from the application's console logs."""

import logging
import re


RESCHEDULE_PATH = re.compile(r"(/(?:en/)?book/reschedule/)[^\s/?\"']+")


class RescheduleLinkPrivacyFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        request = getattr(record, "request", None)
        if RESCHEDULE_PATH.search(message) or RESCHEDULE_PATH.search(getattr(request, "path", "")):
            record.msg = RESCHEDULE_PATH.sub(r"\1[redacted]", message)
            record.args = ()
            # Error-report request/traceback objects can retain the capability.
            record.request = None
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True
