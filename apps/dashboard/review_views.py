from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.core import review_moderation
from apps.core.models import AuditLog
from apps.patients.localization import use_page_language

from .review_forms import PatientReviewActionForm
from .views import _dashboard_home_context, _dashboard_language, _staff_required


def _review_permission(*permissions):
    def decorate(view):
        @wraps(view)
        def permitted(request, *args, **kwargs):
            if not any(request.user.has_perm(f"core.{permission}_publicreview") for permission in permissions):
                return HttpResponseForbidden()
            return view(request, *args, **kwargs)
        return _staff_required(permitted)
    return decorate


def _review_url(language, route="dashboard_patient_reviews", *, page=None, **kwargs):
    params = {"lang": "en"} if language == "en" else {}
    if page and page != 1:
        params["page"] = page
    url = reverse(route, kwargs=kwargs)
    return f"{url}?{urlencode(params)}" if params else url


def _context(request, *, review=None, form=None):
    language = _dashboard_language(request)
    title = "تقييمات المرضى" if language == "ar" else "Patient Reviews"
    context = _dashboard_home_context(request, language=language, metrics={}, schedule_items=[])
    route = "dashboard_patient_review_delete" if review else "dashboard_patient_reviews"
    kwargs = {"review_id": review.pk} if review else {}
    context.update(
        page_key="dashboard_patient_reviews", page_title=title,
        meta_description=title, active_dashboard_nav="reviews",
        canonical_url=request.build_absolute_uri(_review_url(language, route, **kwargs)),
        dashboard_language_switch_url=_review_url("en" if language == "ar" else "ar", route, **kwargs),
        review_list_url=_review_url(language), review=review, form=form,
    )
    return context


@_review_permission("view", "change", "delete")
@require_GET
@use_page_language(language_getter=_dashboard_language)
def patient_review_list(request):
    language = _dashboard_language(request)
    page = Paginator(review_moderation.patient_reviews().order_by("-created_at", "-pk"), 20).get_page(request.GET.get("page"))
    items = []
    for review in page:
        visible = review.is_active and review.is_approved_for_publication
        action = "hide" if visible else "show"
        items.append({
            "review": review, "visible": visible, "action": action,
            "form": PatientReviewActionForm(review=review, action=action),
            "visibility_url": _review_url(language, "dashboard_patient_review_visibility", review_id=review.pk),
            "delete_url": _review_url(language, "dashboard_patient_review_delete", review_id=review.pk),
        })
    context = _context(request)
    context.update(
        review_items=items, page=page,
        previous_url=_review_url(language, page=page.previous_page_number()) if page.has_previous() else "",
        next_url=_review_url(language, page=page.next_page_number()) if page.has_next() else "",
        dashboard_language_switch_url=_review_url("en" if language == "ar" else "ar", page=page.number),
    )
    return render(request, "dashboard/patient_reviews.html", context)


def _action_error(request):
    # No replacement action token on an error response: explicitly reload/read.
    return render(request, "dashboard/patient_review_error.html", _context(request), status=400)


def _audit(request, review, action):
    AuditLog.objects.create(
        user=request.user, app_label="core", model_name="PublicReview", object_id=str(review.pk),
        action=AuditLog.Action.DELETE if action == "delete" else AuditLog.Action.STATUS_CHANGE,
        metadata={"action": f"patient_review_{action}"},
    )


@_review_permission("change")
@require_POST
@use_page_language(language_getter=_dashboard_language)
def patient_review_visibility(request, review_id):
    language = _dashboard_language(request)
    action = request.POST.get("moderation_action")
    with transaction.atomic():
        review = get_object_or_404(review_moderation.patient_reviews().select_for_update(), pk=review_id)
        form = PatientReviewActionForm(request.POST, review=review, action=action)
        if action not in review_moderation.VISIBILITY_ACTIONS or not form.is_valid():
            return _action_error(request)
        review_moderation.set_patient_review_visibility(review, action)
        _audit(request, review, action)
    messages.success(request, (
        "تم إخفاء التقييم." if action == "hide" else "تم إظهار التقييم."
    ) if language == "ar" else ("Review hidden." if action == "hide" else "Review shown."))
    return redirect(_review_url(language))


@_review_permission("delete")
@require_http_methods(["GET", "POST"])
@use_page_language(language_getter=_dashboard_language)
def patient_review_delete(request, review_id):
    language = _dashboard_language(request)
    with transaction.atomic():
        queryset = review_moderation.patient_reviews()
        if request.method == "POST":
            queryset = queryset.select_for_update()
        review = get_object_or_404(queryset, pk=review_id)
        form = PatientReviewActionForm(
            request.POST if request.method == "POST" else None, review=review, action="delete",
        )
        if request.method == "POST":
            if request.POST.get("post") != "yes" or not form.is_valid():
                return _action_error(request)
            _audit(request, review, "delete")
            review.delete()
            messages.success(request, "تم حذف التقييم نهائيًا." if language == "ar" else "Review permanently deleted.")
            return redirect(_review_url(language))
    return render(request, "dashboard/patient_review_delete.html", _context(request, review=review, form=form))
