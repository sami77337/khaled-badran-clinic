"""One exact owner-supplied asset, with the existing identity as fallback."""

from django import template
from django.contrib.staticfiles import finders

register = template.Library()
APPROVED_LOGO_PATH = "img/brand/kb-approved.png"


@register.simple_tag
def approved_logo_path():
    return APPROVED_LOGO_PATH if finders.find(APPROVED_LOGO_PATH) else ""
