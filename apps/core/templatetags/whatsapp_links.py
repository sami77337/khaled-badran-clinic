"""Public WhatsApp entry links for the dedicated clinic bot number."""

from django import template

register = template.Library()

WHATSAPP_BOT_NUMBER = "962798898510"


@register.simple_tag
def whatsapp_bot_url(language="ar"):
    return f"https://wa.me/{WHATSAPP_BOT_NUMBER}"
