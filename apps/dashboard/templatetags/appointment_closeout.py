from django import template

from apps.booking.operations import needs_classification_queryset


register = template.Library()


@register.simple_tag
def appointment_needs_classification_count():
    return needs_classification_queryset().count()
