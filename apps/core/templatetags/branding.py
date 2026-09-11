"""Exact owner-approved brand assets, with the existing identity as fallback."""

from django import template
from django.contrib.staticfiles import finders

register = template.Library()
APPROVED_LOGO_PATH = "img/brand/KB_APPROVED_WEB_512.png"
APPROVED_FAVICON_PATH = "img/brand/KB_APPROVED_256.png"
APPROVED_APPLE_TOUCH_ICON_PATH = "img/brand/KB_APPROVED_APPLE_TOUCH_180.png"


@register.simple_tag
def approved_logo_path():
    return APPROVED_LOGO_PATH if finders.find(APPROVED_LOGO_PATH) else ""


@register.simple_tag
def approved_favicon_path():
    return APPROVED_FAVICON_PATH if finders.find(APPROVED_FAVICON_PATH) else ""


@register.simple_tag
def approved_apple_touch_icon_path():
    return (
        APPROVED_APPLE_TOUCH_ICON_PATH
        if finders.find(APPROVED_APPLE_TOUCH_ICON_PATH)
        else ""
    )
