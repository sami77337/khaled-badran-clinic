import secrets

from django.conf import settings
from django.utils.module_loading import import_string


class WhatsAppOtpServiceUnavailable(RuntimeError):
    pass


def generate_otp_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _send_whatsapp_otp(*, setting_name, phone_e164, code, language):
    """Send through an owner-configured callable; no provider is selected here."""
    sender = getattr(settings, setting_name, "")
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


def send_account_phone_change_otp(phone_e164, code, language):
    return _send_whatsapp_otp(
        setting_name="ACCOUNT_PHONE_CHANGE_OTP_SENDER",
        phone_e164=phone_e164,
        code=code,
        language=language,
    )


def send_appointment_link_recovery_otp(phone_e164, code, language):
    return _send_whatsapp_otp(
        setting_name="APPOINTMENT_LINK_RECOVERY_OTP_SENDER",
        phone_e164=phone_e164,
        code=code,
        language=language,
    )
