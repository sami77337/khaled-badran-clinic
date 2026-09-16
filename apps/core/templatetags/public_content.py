from django import template

from apps.core.models import PublicSiteContent
from apps.core.public_copy import copy_definitions

register = template.Library()


def _overrides(context):
    # Cache per render, never across users/requests or in offline storage.
    request = context.get("request")
    if request is not None:
        if not hasattr(request, "_public_copy_overrides"):
            request._public_copy_overrides = {
                row.key: row for row in PublicSiteContent.objects.all()
            }
        return request._public_copy_overrides
    cache = context.render_context
    if "public_copy_overrides" not in cache:
        cache["public_copy_overrides"] = {
            row.key: row for row in PublicSiteContent.objects.all()
        }
    return cache["public_copy_overrides"]


@register.simple_tag(takes_context=True)
def public_text(context, key, fallback=None):
    definitions = copy_definitions()
    if key not in definitions:
        return ""
    language = "en" if context.get("language") == "en" else "ar"
    row = _overrides(context).get(key)
    value = getattr(row, f"text_{language}", "").strip()
    return value or (
        fallback if fallback is not None else definitions[key][language == "en"]
    )


@register.simple_tag(takes_context=True)
def home_section_visibility(context):
    from apps.core.public_copy import HOME_VISIBILITY

    rows = _overrides(context)
    return {
        key.removeprefix("home.section_"): rows[key].is_visible if key in rows else True
        for key in HOME_VISIBILITY
    }


@register.simple_tag(takes_context=True)
def public_service_groups(context):
    from apps.core.views import SERVICE_GROUPS

    return [
        {
            "title": public_text(context, f"services.group_{index}_title"),
            "bullet_items": public_text(
                context, f"services.group_{index}_items"
            ).splitlines(),
        }
        for index in range(len(SERVICE_GROUPS["ar"]))
    ]
