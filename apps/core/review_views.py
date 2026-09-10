from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from . import views as core_views
from .models import PublicReview
from .showcase import approved_reviews, review_source_summary


REVIEW_PAGE_COPY = {
    "ar": {
        "title": "آراء المرضى",
        "description": "آراء عامة معتمدة عن عيادة الدكتور خالد بدران.",
        "headline": "آراء المرضى",
        "subtitle": "تقييمات عامة معتمدة من مصادرها الأصلية.",
    },
    "en": {
        "title": "Patient Reviews",
        "description": "Approved public reviews for Dr. Khaled Badran Clinic.",
        "headline": "Patient Reviews",
        "subtitle": "Approved public feedback shown from its original source.",
    },
}

FILTERS = {"all", PublicReview.Language.ARABIC, PublicReview.Language.ENGLISH}


@require_GET
def reviews(request, language="ar"):
    language = core_views._normalize_language(language)
    selected_filter = request.GET.get("filter", "all")
    if selected_filter not in FILTERS:
        selected_filter = "all"
    review_language = None if selected_filter == "all" else selected_filter

    context = core_views._base_context(
        request,
        "home",
        language,
        use_public_shell=True,
        show_mobile_booking_cta=True,
    )
    page = REVIEW_PAGE_COPY[language]
    current_route = "reviews_en" if language == "en" else "reviews"
    alternate_route = "reviews" if language == "en" else "reviews_en"
    context.update(
        {
            "page_key": "reviews",
            "page": page,
            "page_title": f"{page['title']} | {context['clinic']['name_ar'] if language == 'ar' else context['clinic']['name_en']}",
            "meta_description": page["description"],
            "canonical_url": request.build_absolute_uri(reverse(current_route)),
            "language_switch": {
                "label": "English" if language == "ar" else "العربية",
                "url": reverse(alternate_route),
            },
            "reviews": approved_reviews(language=review_language),
            "review_summary": review_source_summary(),
            "selected_review_filter": selected_filter,
        }
    )
    return render(request, "core/reviews.html", context)
