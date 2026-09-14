"""Patient rows show visibility, while imported rows keep Django's controls."""

from django import template
from django.contrib.admin.templatetags.admin_list import result_list
from django.utils.html import format_html

from apps.core.models import PublicReview

register = template.Library()


@register.inclusion_tag("admin/change_list_results.html")
def review_result_list(cl):
    context = result_list(cl)
    for review, row in zip(cl.result_list, context["results"]):
        if review.source != PublicReview.Source.PATIENT_PORTAL:
            continue
        for index, field in enumerate(cl.list_display):
            if field == "is_approved_for_publication":
                row[index] = format_html(
                    '<td class="field-publication_status">{}</td>',
                    cl.model_admin.publication_status(review),
                )
            elif field in cl.model_admin.moderation_fields:
                row[index] = format_html('<td>{}</td>', "—")
    return context
