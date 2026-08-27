from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from django.urls import reverse

from apps.records.models import RecordMedia

from .models import PublicReview, SystemSetting


GOOGLE_REVIEW_AVERAGE_KEY = "google_review_average_rating"
GOOGLE_REVIEW_COUNT_KEY = "google_review_count"


def approved_reviews(*, language=None, limit=None):
    queryset = PublicReview.objects.filter(
        is_approved_for_publication=True,
        is_active=True,
    ).exclude(body="")
    if language in {PublicReview.Language.ARABIC, PublicReview.Language.ENGLISH}:
        queryset = queryset.filter(language=language)
    queryset = queryset.order_by("-is_featured", "display_order", "-reviewed_at", "id")
    if limit is not None:
        queryset = queryset[:limit]
    return list(queryset)


def review_source_summary():
    rows = {
        item.key: item.value.strip()
        for item in SystemSetting.objects.filter(
            key__in=[GOOGLE_REVIEW_AVERAGE_KEY, GOOGLE_REVIEW_COUNT_KEY]
        )
    }
    average_raw = rows.get(GOOGLE_REVIEW_AVERAGE_KEY, "")
    count_raw = rows.get(GOOGLE_REVIEW_COUNT_KEY, "")
    if not average_raw or not count_raw:
        return None
    try:
        average = Decimal(average_raw)
        count = int(count_raw)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if average < 0 or average > 5 or count < 0:
        return None
    return {
        "average_rating": format(average.quantize(Decimal("0.1")), "f"),
        "review_count": count,
        "source": "Google",
    }


def _public_media_queryset():
    return (
        RecordMedia.objects.filter(
            visibility=RecordMedia.Visibility.APPROVED_PUBLIC_CASE,
            consent_confirmed=True,
            is_active=True,
        )
        .exclude(file="")
        .select_related("visit")
        .order_by("-uploaded_at", "-public_id")
    )


def _media_url(media, language):
    route = "public_case_media_en" if language == "en" else "public_case_media"
    return reverse(route, kwargs={"public_id": media.public_id})


def _role_from_title(title):
    normalized = (title or "").strip().casefold()
    if normalized in {"قبل", "before"} or normalized.startswith("قبل ") or normalized.startswith("before "):
        return "before"
    if normalized in {"بعد", "after"} or normalized.startswith("بعد ") or normalized.startswith("after "):
        return "after"
    return "primary"


def grouped_public_cases(language="ar", limit=None):
    language = "en" if language == "en" else "ar"
    groups = OrderedDict()
    for media in _public_media_queryset():
        group_key = f"visit:{media.visit_id}" if media.visit_id else f"media:{media.public_id}"
        group = groups.setdefault(
            group_key,
            {
                "key": group_key,
                "items": [],
                "primary": None,
                "before": None,
                "after": None,
                "description": "",
                "public_title": "",
            },
        )
        role = (
            _role_from_title(media.title)
            if media.media_type == RecordMedia.MediaType.IMAGE
            else "primary"
        )
        item = {
            "public_id": media.public_id,
            "media_type": media.media_type,
            "title": media.title,
            "description": media.description,
            "url": _media_url(media, language),
            "role": role,
        }
        group["items"].append(item)
        if media.description and not group["description"]:
            group["description"] = media.description
        if item["role"] == "primary" and media.title and not group["public_title"]:
            group["public_title"] = media.title
        if item["role"] == "before" and group["before"] is None:
            group["before"] = item
        elif item["role"] == "after" and group["after"] is None:
            group["after"] = item
        if group["primary"] is None or (
            item["media_type"] == RecordMedia.MediaType.SHORT_VIDEO
            and group["primary"]["media_type"] != RecordMedia.MediaType.SHORT_VIDEO
        ):
            group["primary"] = item

    result = []
    for index, group in enumerate(groups.values(), start=1):
        neutral_title = (
            f"حالة مصرح بعرضها {index}"
            if language == "ar"
            else f"Authorized case {index}"
        )
        group["display_title"] = group["public_title"] or neutral_title
        result.append(group)
        if limit is not None and len(result) >= limit:
            break
    return result
