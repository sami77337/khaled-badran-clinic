from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.doctor_sections import BUILTIN_SECTIONS, section_controls
from apps.core.models import (
    AuditLog,
    DoctorPageContent,
    DoctorPageSection,
    PublicSiteContent,
)
from apps.core.public_copy import PAGE_LABELS
from apps.core.storage import schedule_public_site_file_deletion
from apps.core.views import _active_doctor
from apps.patients.localization import use_page_language

from .owner_forms import (
    DashboardPasswordChangeForm,
    DoctorBioForm,
    DoctorSectionForm,
    PublicCopyForm,
)
from .views import _dashboard_home_context, _dashboard_language, _staff_required


def _url(request, name="dashboard_content", **kwargs):
    return reverse(name, kwargs=kwargs) + (
        "?lang=en" if _dashboard_language(request) == "en" else ""
    )


def _context(request, title, **extra):
    language = _dashboard_language(request)
    context = _dashboard_home_context(
        request, language=language, metrics={}, schedule_items=[]
    )
    context.update(
        page_title=title,
        form_title=title,
        active_dashboard_nav="content",
        dashboard_language_switch_url=request.path
        + ("?lang=en" if language == "ar" else ""),
        cancel_url=_url(request),
        **extra,
    )
    return context


def _allowed(user, model, instance=None):
    # Owner-approved clinic rule: authenticated staff (doctor and clinic team)
    # share access to the controlled Website Content Manager. Public/patient
    # users remain excluded by the staff boundary.
    return bool(user.is_authenticated and user.is_staff)


def _require(user, model, instance=None):
    if not _allowed(user, model, instance):
        raise PermissionDenied


def _audit(request, instance):
    AuditLog.objects.create(
        user=request.user,
        action=AuditLog.Action.UPDATE,
        app_label="core",
        model_name=instance.__class__.__name__,
        object_id=str(instance.pk),
        metadata={"event": "public_content_saved"},
    )


def _saved(request):
    messages.success(
        request,
        "تم حفظ محتوى الموقع."
        if _dashboard_language(request) == "ar"
        else "Website content saved.",
    )
    return redirect(_url(request))


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@_staff_required
@csrf_protect
@require_http_methods(["GET", "POST"])
@use_page_language(language_getter=_dashboard_language)
def password_change(request):
    language = _dashboard_language(request)
    form = DashboardPasswordChangeForm(
        request.user,
        request.POST if request.method == "POST" else None,
        language=language,
    )
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(
            request,
            "تم تغيير كلمة المرور." if language == "ar" else "Password changed.",
        )
        return redirect(_url(request, "dashboard_password_change"))
    title = "تغيير كلمة المرور" if language == "ar" else "Change Password"
    context = _context(request, title, form=form, password_page=True)
    context["active_dashboard_nav"] = "account"
    context["cancel_url"] = context["dashboard_home_url"]
    return render(request, "dashboard/owner_form.html", context)


@_staff_required
@require_GET
def content_index(request):
    language = _dashboard_language(request)
    doctor = _active_doctor()
    legacy = DoctorPageContent.objects.filter(doctor=doctor).first() if doctor else None
    sections = []
    for section in section_controls(doctor) if doctor else []:
        definition = BUILTIN_SECTIONS.get(section.key)
        title = getattr(section, f"title_{language}") or (
            definition[2 if language == "en" else 1] if definition else "—"
        )
        editable = _allowed(request.user, DoctorPageSection, section)
        if section.key:
            editable = editable and _allowed(request.user, DoctorPageContent, legacy)
        sections.append(
            {
                "section": section,
                "title": title,
                "edit_url": _url(
                    request,
                    "dashboard_doctor_section",
                    section_key=section.key or f"custom-{section.pk}",
                )
                if editable
                else "",
            }
        )
    title = "محتوى الموقع" if language == "ar" else "Website Content"
    return render(
        request,
        "dashboard/content_index.html",
        _context(
            request,
            title,
            sections=sections,
            content_doctor=doctor,
            bio_url=_url(request, "dashboard_doctor_bio")
            if doctor and _allowed(request.user, DoctorPageContent, legacy)
            else "",
            new_section_url=_url(request, "dashboard_doctor_section_new")
            if doctor and _allowed(request.user, DoctorPageSection)
            else "",
            copy_pages=[
                {
                    "label": labels[language == "en"],
                    "url": _url(request, "dashboard_public_copy", page=page),
                }
                for page, labels in PAGE_LABELS.items()
            ],
        ),
    )


@_staff_required
@csrf_protect
@require_http_methods(["GET", "POST"])
@use_page_language(language_getter=_dashboard_language)
def doctor_bio(request):
    doctor = _active_doctor()
    if doctor is None:
        raise Http404
    with transaction.atomic():
        # Serialize creation/editing for this existing public doctor only.
        type(doctor).objects.select_for_update().get(pk=doctor.pk)
        content = DoctorPageContent.objects.filter(
            doctor=doctor
        ).first() or DoctorPageContent(doctor=doctor)
        _require(request.user, DoctorPageContent, content)
        language = _dashboard_language(request)
        old_photo_name = content.profile_photo.name if content.profile_photo else ""
        old_photo_storage = content.profile_photo.storage if old_photo_name else None
        form = DoctorBioForm(
            request.POST if request.method == "POST" else None,
            request.FILES if request.method == "POST" else None,
            instance=content,
            language=language,
        )
        if request.method == "POST" and form.is_valid():
            saved = form.save()
            new_photo_name = saved.profile_photo.name if saved.profile_photo else ""
            if (
                old_photo_storage is not None
                and old_photo_name
                and old_photo_name != new_photo_name
            ):
                schedule_public_site_file_deletion(
                    old_photo_storage, old_photo_name
                )
            _audit(request, saved)
            return _saved(request)
    title = (
        "بيانات وصورة الطبيب" if language == "ar" else "Doctor Profile & Photo"
    )
    current_photo_url = (
        reverse("dashboard_doctor_public_photo")
        if old_photo_name
        else static("img/doctor/dr-khaled-badran.png")
    )
    return render(
        request,
        "dashboard/owner_form.html",
        _context(
            request,
            title,
            form=form,
            fallback_help=True,
            doctor_photo_page=True,
            current_photo_url=current_photo_url,
        ),
    )


@_staff_required
@csrf_protect
@require_http_methods(["GET", "POST"])
@use_page_language(language_getter=_dashboard_language)
def doctor_section(request, section_key=None):
    doctor = _active_doctor()
    if doctor is None:
        raise Http404
    language = _dashboard_language(request)
    with transaction.atomic():
        type(doctor).objects.select_for_update().get(pk=doctor.pk)
        if section_key is None:
            section = DoctorPageSection(doctor=doctor, is_visible=False)
        else:
            section = next(
                (
                    row
                    for row in section_controls(doctor)
                    if (row.key or f"custom-{row.pk}") == section_key
                ),
                None,
            )
            if section is None:
                raise Http404
        _require(request.user, DoctorPageSection, section)
        legacy = None
        if section.key:
            legacy = DoctorPageContent.objects.filter(
                doctor=doctor
            ).first() or DoctorPageContent(doctor=doctor)
            _require(request.user, DoctorPageContent, legacy)
        form = DoctorSectionForm(
            request.POST if request.method == "POST" else None,
            instance=section,
            legacy=legacy,
            language=language,
        )
        if request.method == "POST" and form.is_valid():
            _audit(request, form.save())
            return _saved(request)
    title = "قسم في صفحة الطبيب" if language == "ar" else "Doctor Page Section"
    return render(
        request,
        "dashboard/owner_form.html",
        _context(
            request,
            title,
            form=form,
            fallback_help=bool(section.key),
            section_page=True,
        ),
    )


@_staff_required
@csrf_protect
@require_http_methods(["GET", "POST"])
@use_page_language(language_getter=_dashboard_language)
def public_copy(request, page):
    if page not in PAGE_LABELS:
        raise Http404
    language = _dashboard_language(request)
    overrides = {
        row.key: row
        for row in PublicSiteContent.objects.filter(key__startswith=page + ".")
    }
    form = PublicCopyForm(
        request.POST if request.method == "POST" else None,
        page=page,
        overrides=overrides,
        language=language,
        doctor=_active_doctor() if page == "home" else None,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            for key in form.copy_keys:
                values = {
                    f"text_{lang}": form.cleaned_data[form.field_name(key, lang)]
                    for lang in ("ar", "en")
                }
                if key in overrides or any(values.values()):
                    row, _ = PublicSiteContent.objects.update_or_create(
                        key=key, defaults=values
                    )
                    _audit(request, row)
            for key in form.visibility_keys:
                visible = form.cleaned_data[form.field_name(key)]
                if key in overrides or not visible:
                    row, _ = PublicSiteContent.objects.update_or_create(
                        key=key, defaults={"is_visible": visible}
                    )
                    _audit(request, row)
        return _saved(request)
    return render(
        request,
        "dashboard/owner_form.html",
        _context(
            request, PAGE_LABELS[page][language == "en"], form=form, fallback_help=True
        ),
    )
