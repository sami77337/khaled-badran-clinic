from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from django.urls import reverse

from apps.records.models import RecordMedia
from apps.records.public_cases import (
    PUBLIC_CASE_ROLE_AFTER,
    PUBLIC_CASE_ROLE_BEFORE,
    PUBLIC_CASE_ROLE_VIDEO,
    PUBLIC_CASE_ROLE_VIDEO_COVER,
)

from .models import PublicReview, SystemSetting


GOOGLE_REVIEW_AVERAGE_KEY = "google_review_average_rating"
GOOGLE_REVIEW_COUNT_KEY = "google_review_count"

CAROUSEL_ROLE_LABELS = {
    "ar": {
        RecordMedia.PublicCaseRole.BEFORE: "\u0642\u0628\u0644",
        RecordMedia.PublicCaseRole.AFTER: "\u0628\u0639\u062f",
        RecordMedia.PublicCaseRole.VIDEO: "\u0641\u064a\u062f\u064a\u0648",
        RecordMedia.PublicCaseRole.PRIMARY: "\u0635\u0648\u0631\u0629 \u0627\u0644\u062d\u0627\u0644\u0629",
    },
    "en": {
        RecordMedia.PublicCaseRole.BEFORE: "Before",
        RecordMedia.PublicCaseRole.AFTER: "After",
        RecordMedia.PublicCaseRole.VIDEO: "Video",
        RecordMedia.PublicCaseRole.PRIMARY: "Case Image",
    },
}


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
            trashed_at__isnull=True,
            public_case__consent_confirmed=True,
            public_case__is_published=True,
        )
        .exclude(file="")
        .select_related("public_case")
        .order_by(
            "-public_case__created_at",
            "-public_case_id",
            "-uploaded_at",
            "-public_id",
        )
    )


def _media_url(media, language):
    route = "public_case_media_en" if language == "en" else "public_case_media"
    return reverse(route, kwargs={"public_id": media.public_id})


def _label_carousel_category(items, role, language):
    total = len(items)
    role_label = CAROUSEL_ROLE_LABELS[language][role]
    for position, item in enumerate(items, start=1):
        separator = " \u0645\u0646 " if language == "ar" else " of "
        item["label"] = f"{role_label} {position}{separator}{total}"
        item["category_position"] = position
        item["category_total"] = total
    return items


def grouped_public_cases(language="ar", limit=None, case_id=None):
    language = "en" if language == "en" else "ar"
    groups = OrderedDict()
    queryset = _public_media_queryset()
    if case_id is not None:
        queryset = queryset.filter(public_case_id=case_id)
    for media in queryset:
        public_case = media.public_case
        group_key = f"case:{public_case.pk}"
        group = groups.setdefault(
            group_key,
            {
                "key": group_key,
                "items": [],
                "primary": None,
                "teaser": None,
                "before": None,
                "after": None,
                "before_items": [],
                "after_items": [],
                "primary_items": [],
                "video_items": [],
                "video_cover": None,
                "carousel_items": [],
                "case_id": public_case.pk,
                "description": (public_case.note or "").strip(),
                "public_title": (public_case.title or "").strip(),
            },
        )
        role = media.public_case_role or RecordMedia.PublicCaseRole.PRIMARY
        if media.media_type == RecordMedia.MediaType.SHORT_VIDEO:
            role = PUBLIC_CASE_ROLE_VIDEO
        elif role == PUBLIC_CASE_ROLE_VIDEO:
            role = RecordMedia.PublicCaseRole.PRIMARY
        item = {
            "public_id": media.public_id,
            "media_type": media.media_type,
            "url": _media_url(media, language),
            "role": role,
            "poster_url": "",
        }
        group["items"].append(item)

        if role == PUBLIC_CASE_ROLE_VIDEO_COVER:
            if group["video_cover"] is None:
                group["video_cover"] = item
        elif role == PUBLIC_CASE_ROLE_BEFORE:
            group["before_items"].append(item)
        elif role == PUBLIC_CASE_ROLE_AFTER:
            group["after_items"].append(item)
        elif media.media_type == RecordMedia.MediaType.SHORT_VIDEO:
            group["video_items"].append(item)
        elif role == RecordMedia.PublicCaseRole.PRIMARY:
            group["primary_items"].append(item)

    result = []
    for group in groups.values():
        group["before"] = group["before_items"][0] if group["before_items"] else None
        group["after"] = group["after_items"][0] if group["after_items"] else None
        valid_video_cover = (
            group["video_cover"]
            if group["video_items"] and group["video_cover"]
            else None
        )
        if valid_video_cover and group["video_items"]:
            group["video_items"][0]["poster_url"] = valid_video_cover["url"]
        primary_images = group["primary_items"]
        before_slides = _label_carousel_category(
            group["before_items"],
            RecordMedia.PublicCaseRole.BEFORE,
            language,
        )
        after_slides = _label_carousel_category(
            group["after_items"],
            RecordMedia.PublicCaseRole.AFTER,
            language,
        )
        primary_slides = _label_carousel_category(
            primary_images,
            RecordMedia.PublicCaseRole.PRIMARY,
            language,
        )
        video_slides = _label_carousel_category(
            group["video_items"],
            RecordMedia.PublicCaseRole.VIDEO,
            language,
        )
        group["carousel_items"] = (
            video_slides + before_slides + after_slides + primary_slides
            if valid_video_cover
            else before_slides + after_slides + primary_slides + video_slides
        )
        group["primary"] = (
            group["video_items"][0]
            if group["video_items"]
            else (
                primary_images[0]
                if primary_images
                else (group["before"] or group["after"])
            )
        )
        group["cover"] = (
            valid_video_cover
            or group["before"]
            or group["after"]
            or (primary_images[0] if primary_images else None)
            or (group["video_items"][0] if group["video_items"] else None)
        )
        group["teaser"] = group["cover"]
        if group["cover"] is None:
            continue
        index = len(result) + 1
        neutral_title = (
            f"حالة مصرح بعرضها {index}"
            if language == "ar"
            else f"Authorized case {index}"
        )
        group["display_title"] = group["public_title"] or neutral_title
        group["detail_url"] = reverse(
            "public_case_detail_en" if language == "en" else "public_case_detail",
            kwargs={"case_id": group["case_id"]},
        )
        group["counts"] = {
            "videos": len(group["video_items"]),
            "before": len(group["before_items"]),
            "after": len(group["after_items"]),
            "primary": len(group["primary_items"]),
        }
        result.append(group)
        if limit is not None and len(result) >= limit:
            break
    return result
