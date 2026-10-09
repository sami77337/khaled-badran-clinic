from functools import wraps

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.models import (
    AuditLog,
    PORTAL_REVIEW_PUBLICATION_CONSENT_VERSION,
    PublicReview,
)
from .localization import use_page_language
from .review_forms import PatientReviewForm
from .views import _authenticated_portal_context, _login_required, _portal_url


def _patient_required(view):
    @wraps(view)
    def patient_only(request, *args, **kwargs):
        if not request.user.is_active or request.user.is_staff or request.user.is_superuser:
            return HttpResponseForbidden()
        return view(request, *args, **kwargs)
    return _login_required(patient_only)


def _own_reviews(user):
    return PublicReview.objects.filter(submitted_by=user, source=PublicReview.Source.PATIENT_PORTAL)


def _record_publication_consent(request, review, language):
    # Each publish/revision leaves bounded metadata evidence, not a second
    # copy of the patient's public text or display name.
    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.STATUS_CHANGE,
        app_label="core",
        model_name="PublicReview",
        object_id=str(review.pk),
        metadata={
            "action": "patient_review_publication_consent",
            "version": PORTAL_REVIEW_PUBLICATION_CONSENT_VERSION,
            "language": language,
        },
    )


def _review_context(request, language, review, *, form=None, editing=False):
    status = (
        "published"
        if review and review.is_active and review.is_approved_for_publication
        and review.publication_withdrawn_at is None
        else "hidden"
    )
    title = "تقييمي" if language == "ar" else "My Review"
    return _authenticated_portal_context(
        request, language, page_title=title, portal_section="review",
        review=review, review_status=status, form=form, editing=editing,
        review_url=_portal_url("patient_portal_review", language),
        review_edit_url=_portal_url("patient_portal_review_edit", language, review_id=review.pk) if review else "",
        review_delete_url=_portal_url("patient_portal_review_delete", language, review_id=review.pk) if review else "",
        review_withdraw_url=_portal_url("patient_portal_review_withdraw", language, review_id=review.pk) if review else "",
    )


@_patient_required
@require_http_methods(["GET", "POST"])
@use_page_language
def my_review(request, language="ar"):
    review = _own_reviews(request.user).first()
    if review is not None:
        if request.method == "POST":
            messages.info(request, "لديك تقييم بالفعل. يمكنك تعديله." if language == "ar" else "You already have a review. You can edit it.")
            return redirect(_portal_url("patient_portal_review", language))
        return render(request, "patients/my_review.html", _review_context(request, language, review))

    form = PatientReviewForm(
        request.POST if request.method == "POST" else None,
        language=language,
        instance=PublicReview(
            submitted_by=request.user, source=PublicReview.Source.PATIENT_PORTAL,
            language=language, is_approved_for_publication=False, is_active=True, is_featured=False,
            reviewed_at=timezone.localdate(),
        ),
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                review = form.save(commit=False)
                review.is_approved_for_publication = True
                review.is_active = True
                review.is_featured = False
                review.publication_consent_at = timezone.now()
                review.publication_consent_version = PORTAL_REVIEW_PUBLICATION_CONSENT_VERSION
                review.publication_consent_language = language
                review.publication_withdrawn_at = None
                review.save()
                _record_publication_consent(request, review, language)
        except IntegrityError:
            # Concurrent submissions are bounded by the scoped database constraint.
            if not _own_reviews(request.user).exists():
                raise
            messages.info(request, "لديك تقييم بالفعل. يمكنك تعديله." if language == "ar" else "You already have a review. You can edit it.")
        else:
            messages.success(request, "تم نشر تقييمك مباشرة." if language == "ar" else "Your review is now published.")
        return redirect(_portal_url("patient_portal_review", language))
    return render(request, "patients/my_review.html", _review_context(request, language, None, form=form))


@_patient_required
@require_http_methods(["GET", "POST"])
@use_page_language
def edit_review(request, review_id, language="ar"):
    with transaction.atomic():
        queryset = _own_reviews(request.user)
        if request.method == "POST":
            queryset = queryset.select_for_update()
        review = get_object_or_404(queryset, pk=review_id)
        form = PatientReviewForm(request.POST if request.method == "POST" else None, instance=review, language=language)
        if request.method == "POST" and form.is_valid():
            updated = form.save(commit=False)
            updated.is_approved_for_publication = True
            updated.is_featured = False
            updated.is_active = True
            updated.publication_consent_at = timezone.now()
            updated.publication_consent_version = PORTAL_REVIEW_PUBLICATION_CONSENT_VERSION
            updated.publication_consent_language = language
            updated.publication_withdrawn_at = None
            updated.save(update_fields=[
                "reviewer_name", "rating", "body", "is_approved_for_publication",
                "is_featured", "is_active", "publication_consent_at",
                "publication_consent_version", "publication_consent_language",
                "publication_withdrawn_at", "updated_at",
            ])
            _record_publication_consent(request, updated, language)
            messages.success(request, "تم حفظ التعديلات ونشر التقييم مباشرة." if language == "ar" else "Changes saved and published immediately.")
            return redirect(_portal_url("patient_portal_review", language))
    return render(request, "patients/my_review.html", _review_context(request, language, review, form=form, editing=True))


@_patient_required
@require_POST
def delete_review(request, review_id, language="ar"):
    with transaction.atomic():
        review = get_object_or_404(_own_reviews(request.user).select_for_update(), pk=review_id)
        review.delete()
    messages.success(request, "تم حذف تقييمك نهائيًا." if language == "ar" else "Your review was permanently deleted.")
    return redirect(_portal_url("patient_portal_review", language))


@_patient_required
@require_POST
@use_page_language
def withdraw_review(request, review_id, language="ar"):
    """Stop publication without deleting patient-authored text or prior evidence."""
    with transaction.atomic():
        review = get_object_or_404(
            _own_reviews(request.user).select_for_update(), pk=review_id
        )
        if review.publication_withdrawn_at is None:
            review.publication_withdrawn_at = timezone.now()
            review.is_approved_for_publication = False
            review.is_active = False
            review.save(update_fields=[
                "publication_withdrawn_at", "is_approved_for_publication",
                "is_active", "updated_at",
            ])
            # No review text, display name, phone number or source metadata.
            AuditLog.objects.create(
                user=request.user,
                action=AuditLog.Action.STATUS_CHANGE,
                app_label="core",
                model_name="PublicReview",
                object_id=str(review.pk),
                metadata={"action": "patient_review_publication_withdrawn"},
            )
    messages.success(
        request,
        "تم إيقاف نشر تقييمك. يمكنك نشره مجددًا بعد موافقة جديدة."
        if language == "ar" else
        "Your review is no longer public. You can republish it with new consent.",
    )
    return redirect(_portal_url("patient_portal_review", language))
