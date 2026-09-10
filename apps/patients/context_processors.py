from django.db.models import Count, Q, Window
from django.urls import reverse

from apps.patients.models import ConsultationNotification


def _notification_language(request):
    resolver_match = getattr(request, "resolver_match", None)
    route_language = (
        resolver_match.kwargs.get("language")
        if resolver_match and resolver_match.kwargs
        else None
    )
    if route_language == "en" or request.GET.get("lang") == "en":
        return "en"
    if request.path.startswith("/en/"):
        return "en"
    return "ar"


def consultation_notifications(request):
    context = {
        "consultation_notification_items": (),
        "consultation_notification_unread_count": 0,
        "consultation_notification_unread_badge": "",
    }
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return context

    language = _notification_language(request)
    if user.is_staff:
        kind = ConsultationNotification.Kind.NEW_CONSULTATION
        consultations_url = reverse("dashboard_consultation_list")
        if language == "en":
            consultations_url = f"{consultations_url}?lang=en"
    else:
        kind = ConsultationNotification.Kind.CONSULTATION_REPLIED
        route = "patient_portal_consultation_list_en" if language == "en" else "patient_portal_consultation_list"
        consultations_url = reverse(route)

    notifications = ConsultationNotification.objects.filter(
        recipient=user,
        kind=kind,
    )
    notification_items = tuple(
        notifications.annotate(
            notification_unread_total=Window(
                expression=Count("pk", filter=Q(read_at__isnull=True)),
            )
        ).values(
            "public_id",
            "kind",
            "read_at",
            "created_at",
            "notification_unread_total",
        )[:10]
    )
    unread_count = (
        notification_items[0]["notification_unread_total"]
        if notification_items
        else 0
    )
    context.update(
        {
            "consultation_notification_items": notification_items,
            "consultation_notification_unread_count": unread_count,
            "consultation_notification_unread_badge": (
                "99+" if unread_count > 99 else str(unread_count) if unread_count else ""
            ),
            "consultation_notification_open_route": (
                "consultation_notification_open_en"
                if language == "en"
                else "consultation_notification_open"
            ),
            "consultation_notification_mark_all_url": reverse(
                "consultation_notifications_mark_all_read_en"
                if language == "en"
                else "consultation_notifications_mark_all_read"
            ),
            "consultation_notification_consultations_url": consultations_url,
        }
    )
    return context
