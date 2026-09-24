from django.db.models import Count, Q, Window
from django.urls import reverse

from apps.booking.models import AppointmentStaffNotification
from apps.patients.models import (
    Consultation,
    ConsultationNotification,
    TransientConsultation,
)


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


def _language_url(route_name, language, **kwargs):
    url = reverse(route_name, kwargs=kwargs or None)
    return f"{url}?lang=en" if language == "en" else url


def _staff_attention_context(user, language):
    registered = Consultation.objects.filter(
        staff_reply="",
        audio_reply__isnull=True,
    ).order_by("-created_at", "-id")
    guests = TransientConsultation.objects.filter(
        staff_reply="",
        audio_reply__isnull=True,
    ).order_by("-created_at", "-id")
    booking_notifications = AppointmentStaffNotification.objects.filter(
        recipient=user,
    ).select_related("appointment").order_by("-created_at", "-id")

    registered_count = registered.count()
    guest_count = guests.count()
    booking_unseen_count = booking_notifications.filter(seen_at__isnull=True).count()
    unread_count = registered_count + guest_count + booking_unseen_count

    items = []
    for consultation in registered[:10]:
        items.append(
            {
                "kind": "new_consultation",
                "created_at": consultation.created_at,
                "is_pending": True,
                "open_method": "get",
                "url": _language_url(
                    "dashboard_consultation_detail",
                    language,
                    public_id=consultation.public_id,
                ),
            }
        )
    for consultation in guests[:10]:
        items.append(
            {
                "kind": "new_consultation",
                "created_at": consultation.created_at,
                "is_pending": True,
                "open_method": "get",
                "url": _language_url(
                    "dashboard_guest_consultation_detail",
                    language,
                    public_id=consultation.public_id,
                ),
            }
        )
    appointments_url = _language_url("staff_appointment_list", language)
    for notification in booking_notifications[:10]:
        items.append(
            {
                "kind": "new_booking",
                "created_at": notification.created_at,
                "is_pending": notification.seen_at is None,
                "open_method": "get",
                "url": appointments_url,
            }
        )

    items.sort(key=lambda item: item["created_at"], reverse=True)
    consultations_url = _language_url("dashboard_consultation_list", language)
    return {
        "consultation_notification_items": tuple(items[:10]),
        "consultation_notification_unread_count": unread_count,
        "consultation_notification_unread_badge": (
            "99+" if unread_count > 99 else str(unread_count) if unread_count else ""
        ),
        "consultation_notification_open_route": "",
        "consultation_notification_mark_all_url": reverse(
            "consultation_notifications_mark_all_read_en"
            if language == "en"
            else "consultation_notifications_mark_all_read"
        ),
        "consultation_notification_consultations_url": consultations_url,
        "consultation_notification_staff_mode": True,
        "consultation_notification_booking_unseen_count": booking_unseen_count,
        "consultation_notification_mark_all_enabled": booking_unseen_count > 0,
        "consultation_notification_auto_seen_on_open": booking_unseen_count > 0,
    }


def _patient_notification_context(user, language):
    notifications = ConsultationNotification.objects.filter(
        recipient=user,
        kind=ConsultationNotification.Kind.CONSULTATION_REPLIED,
    )
    notification_items = list(
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
    for item in notification_items:
        item["is_pending"] = item["read_at"] is None
        item["open_method"] = "post"

    unread_count = (
        notification_items[0]["notification_unread_total"]
        if notification_items
        else 0
    )
    route = (
        "patient_portal_consultation_list_en"
        if language == "en"
        else "patient_portal_consultation_list"
    )
    return {
        "consultation_notification_items": tuple(notification_items),
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
        "consultation_notification_consultations_url": reverse(route),
        "consultation_notification_staff_mode": False,
        "consultation_notification_booking_unseen_count": 0,
        "consultation_notification_mark_all_enabled": unread_count > 0,
        "consultation_notification_auto_seen_on_open": False,
    }


def consultation_notifications(request):
    context = {
        "consultation_notification_items": (),
        "consultation_notification_unread_count": 0,
        "consultation_notification_unread_badge": "",
        "consultation_notification_staff_mode": False,
        "consultation_notification_booking_unseen_count": 0,
        "consultation_notification_mark_all_enabled": False,
        "consultation_notification_auto_seen_on_open": False,
    }
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return context

    language = _notification_language(request)
    if user.is_staff and user.is_active:
        context.update(_staff_attention_context(user, language))
    else:
        context.update(_patient_notification_context(user, language))
    return context
