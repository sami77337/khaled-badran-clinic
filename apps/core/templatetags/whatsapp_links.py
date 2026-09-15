"""Public WhatsApp entry links for the dedicated clinic bot number."""

from urllib.parse import urlencode

from django import template

register = template.Library()

WHATSAPP_BOT_NUMBER = "962798898510"


@register.simple_tag
def whatsapp_bot_url(language="ar"):
    language = "en" if language == "en" else "ar"
    text = "start" if language == "en" else "ابدأ"
    return f"https://wa.me/{WHATSAPP_BOT_NUMBER}?{urlencode({'text': text})}"
