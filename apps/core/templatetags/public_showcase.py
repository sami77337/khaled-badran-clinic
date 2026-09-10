from django import template

from apps.core.showcase import approved_reviews, grouped_public_cases, review_source_summary


register = template.Library()


@register.simple_tag
def home_public_reviews(limit=12):
    return approved_reviews(limit=limit)


@register.simple_tag
def public_review_summary():
    return review_source_summary()


@register.simple_tag
def public_case_groups(language="ar", limit=None):
    parsed_limit = None
    if limit not in (None, ""):
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError):
            parsed_limit = None
    return grouped_public_cases(language=language, limit=parsed_limit)
