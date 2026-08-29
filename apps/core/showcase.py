from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from django.urls import reverse

from apps.records.models import RecordMedia
from apps.records.public_cases import (
    PUBLIC_CASE_ROLE_AFTER,
    PUBLIC_CASE_ROLE_BEFORE,
    PUBLIC_CASE_ROLE_VIDEO,
    PUBLIC_CASE_ROLE_VIDEO_COVER,
    decode_public_case_title,
)

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
                "before_items": [],
                "after_items": [],
                "video_items": [],
                "video_cover": None,
                "description": "",
                "public_title": "",
            },
        )
        role, clean_title, is_encoded = decode_public_case_title(media.title)
        decoded_role = role
        if media.media_type == RecordMedia.MediaType.SHORT_VIDEO:
            role = PUBLIC_CASE_ROLE_VIDEO
        elif role == PUBLIC_CASE_ROLE_VIDEO:
            role = "primary"
        item = {
            "public_id": media.public_id,
            "media_type": media.media_type,
            "title": clean_title,
            "description": media.description,
            "url": _media_url(media, language),
            "role": role,
            "poster_url": "",
        }
        group["items"].append(item)
        if media.description and not group["description"]:
            group["description"] = media.description
        if clean_title and (is_encoded or decoded_role == "primary") and not group["public_title"]:
            group["public_title"] = clean_title

        if role == PUBLIC_CASE_ROLE_VIDEO_COVER:
            if group["video_cover"] is None:
                group["video_cover"] = item
        elif role == PUBLIC_CASE_ROLE_BEFORE:
            group["before_items"].append(item)
        elif role == PUBLIC_CASE_ROLE_AFTER:
            group["after_items"].append(item)
        elif media.media_type == RecordMedia.MediaType.SHORT_VIDEO:
            group["video_items"].append(item)

    result = []
    for index, group in enumerate(groups.values(), start=1):
        group["before"] = group["before_items"][0] if group["before_items"] else None
        group["after"] = group["after_items"][0] if group["after_items"] else None
        if group["video_items"] and group["video_cover"]:
            group["video_items"][0]["poster_url"] = group["video_cover"]["url"]
        primary_images = [
            item
            for item in group["items"]
            if item["media_type"] == RecordMedia.MediaType.IMAGE
            and item["role"] == "primary"
        ]
        group["primary"] = (
            group["video_items"][0]
            if group["video_items"]
            else (
                primary_images[0]
                if primary_images
                else (group["before"] or group["after"])
            )
        )
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
