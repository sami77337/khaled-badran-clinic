from django.conf import settings
from django.utils.module_loading import import_string


class WhatsAppOtpServiceUnavailable(RuntimeError):
    pass


def send_account_phone_change_otp(phone_e164, code, language):
    """Send through an owner-configured callable; no provider is selected here."""
    sender = getattr(settings, "ACCOUNT_PHONE_CHANGE_OTP_SENDER", "")
    if not sender:
        raise WhatsAppOtpServiceUnavailable("WhatsApp verification service is unavailable.")
    if isinstance(sender, str):
        sender = import_string(sender)
    if not callable(sender):
        raise WhatsAppOtpServiceUnavailable("WhatsApp verification service is unavailable.")
    try:
        result = sender(phone_e164, code, language)
        if result is False:
            raise WhatsAppOtpServiceUnavailable("WhatsApp verification service is unavailable.")
    except WhatsAppOtpServiceUnavailable:
        raise
    except Exception:
        raise WhatsAppOtpServiceUnavailable("WhatsApp verification service is unavailable.") from None
