from pathlib import PurePosixPath
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, dumps as signing_dumps, loads as signing_loads
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods

from apps.booking import operations as booking_operations
from apps.booking import services as booking_services
from apps.booking.countries import INTERNATIONAL_PHONE_COUNTRIES
from apps.booking.models import Appointment
from apps.core.views import _base_context
from apps.patients import consultation_services, link_recovery, phone_change
from apps.patients import rate_limits, services
from apps.patients.forms import (
    AccountPhoneChangeStartForm,
    AccountPhoneChangeVerifyForm,
    AppointmentLinkForm,
    AppointmentLinkRecoveryStartForm,
    AppointmentLinkRecoveryVerifyForm,
    ConsultationCreateForm,
    PatientLoginForm,
    PatientRegistrationForm,
    StaffLoginForm,
    auth_error_message,
)
from apps.patients.models import (
    AccountPhoneChangeChallenge,
    AppointmentLinkRecoveryChallenge,
    Consultation,
    ConsultationAttachment,
    ConsultationAudioReply,
)
from apps.patients.otp import WhatsAppOtpServiceUnavailable
from apps.patients.profile_resolution import PatientProfileConflictError
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord


_PORTAL_NOTE_TYPE_LABELS = {
    "ar": {
        ClinicalNote.NoteType.DOCTOR_NOTE: "ملاحظة الطبيب",
        ClinicalNote.NoteType.STAFF_NOTE: "ملاحظة فريق العيادة",
        ClinicalNote.NoteType.FOLLOW_UP: "متابعة",
    },
    "en": {
        ClinicalNote.NoteType.DOCTOR_NOTE: "Doctor note",
        ClinicalNote.NoteType.STAFF_NOTE: "Clinic staff note",
        ClinicalNote.NoteType.FOLLOW_UP: "Follow-up",
    },
}

_PORTAL_MEDIA_TYPE_LABELS = {
    "ar": {
        RecordMedia.MediaType.IMAGE: "صورة",
        RecordMedia.MediaType.SHORT_VIDEO: "فيديو قصير",
    },
    "en": {
        RecordMedia.MediaType.IMAGE: "Image",
        RecordMedia.MediaType.SHORT_VIDEO: "Short video",
    },
}

_LINK_RECOVERY_SESSION_KEY = "patient_portal_verified_link_recovery"
_APPOINTMENT_CANCELLATION_SIGNING_SALT = "patients.appointment-cancellation"


def _language(language):
    return "en" if language == "en" else "ar"


def _route_name(name, language):
    return f"{name}_en" if _language(language) == "en" else name


def _portal_url(name, language, **kwargs):
    return reverse(_route_name(name, language), kwargs=kwargs or None)


def _booking_start_url(language):
    return reverse(_route_name("book", language))


def _portal_language_switch_url(request, language):
    language = _language(language)
    alternate_language = "en" if language == "ar" else "ar"
    fallback = _portal_url("patient_portal_dashboard", alternate_language)
    resolver_match = request.resolver_match
    if resolver_match is None or not resolver_match.url_name:
        return fallback

    route_name = resolver_match.url_name
    if not route_name.startswith("patient_portal_"):
        return fallback

    base_route_name = route_name[:-3] if route_name.endswith("_en") else route_name
    alternate_route_name = f"{base_route_name}_en" if alternate_language == "en" else base_route_name
    route_kwargs = dict(resolver_match.kwargs)
    route_kwargs.pop("language", None)
    if "public_token" in route_kwargs:
        return _portal_url("patient_portal_appointment_list", alternate_language)
    try:
        return reverse(alternate_route_name, kwargs=route_kwargs or None)
    except (NoReverseMatch, TypeError, ValueError):
        return fallback


def _portal_note_type_label(note_type, language):
    language = _language(language)
    fallback = "ملاحظة" if language == "ar" else "Note"
    return _PORTAL_NOTE_TYPE_LABELS[language].get(note_type, fallback)


def _portal_media_type_label(media_type, language):
    language = _language(language)
    fallback = "وسائط معتمدة" if language == "ar" else "Approved media"
    return _PORTAL_MEDIA_TYPE_LABELS[language].get(media_type, fallback)


def _login_url(language):
    return reverse(_route_name("login", language))


def _doctor_dashboard_url(language):
    dashboard_url = reverse("dashboard_home")
    return f"{dashboard_url}?lang=en" if _language(language) == "en" else dashboard_url


def _login_url_with_query(language, *, role, next_url=""):
    query = {"role": role}
    if next_url:
        query["next"] = next_url
    return f"{_login_url(language)}?{urlencode(query)}"


def _safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ""


def _token_initial(request):
    return (request.GET.get("token") or request.GET.get("public_token") or "").strip()


def _appointment_cancellation_reference(appointment):
    return signing_dumps(appointment.pk, salt=_APPOINTMENT_CANCELLATION_SIGNING_SALT)


def _appointment_from_cancellation_reference(reference, user):
    try:
        appointment_id = signing_loads(
            reference,
            salt=_APPOINTMENT_CANCELLATION_SIGNING_SALT,
        )
    except (BadSignature, TypeError, ValueError) as exc:
        raise Http404("Appointment unavailable.") from exc
    return get_object_or_404(
        Appointment.objects.select_related("doctor", "patient", "visit_type"),
        pk=appointment_id,
        patient__user=user,
    )


def _portal_context(request, language, **extra):
    language = _language(language)
    context = _base_context(request, "patient_portal", language)
    canonical_path = request.path
    if request.resolver_match and "public_token" in request.resolver_match.kwargs:
        canonical_path = _portal_url("patient_portal_appointment_list", language)
    nav_labels = {
        "ar": {
            "medical_records": "السجل الطبي",
            "dashboard": "الرئيسية",
            "appointments": "المواعيد",
            "book": "حجز موعد",
            "consultations": "استشارة الطبيب",
            "link": "ربط موعد",
            "account": "الحساب",
            "password": "تغيير كلمة المرور",
            "logout": "تسجيل الخروج",
        },
        "en": {
            "medical_records": "Medical Records",
            "dashboard": "Dashboard",
            "appointments": "Appointments",
            "book": "Book Appointment",
            "consultations": "Consultations",
            "link": "Link Appointment",
            "account": "Account",
            "password": "Change Password",
            "logout": "Logout",
        },
    }[language]
    context.update(
        {
            "page_key": "patient_portal",
            "portal_dashboard_url": _portal_url("patient_portal_dashboard", language),
            "portal_login_url": _login_url(language),
            "portal_logout_url": _portal_url("patient_portal_logout", language),
            "portal_register_url": _portal_url("patient_portal_register", language),
            "portal_link_url": _portal_url("patient_portal_link_appointment", language),
            "portal_link_recovery_url": _portal_url(
                "patient_portal_link_appointment_recovery",
                language,
            ),
            "portal_appointments_url": _portal_url("patient_portal_appointment_list", language),
            "portal_book_url": _booking_start_url(language),
            "portal_consultations_url": _portal_url("patient_portal_consultation_list", language),
            "portal_consultation_new_url": _portal_url("patient_portal_consultation_new", language),
            "portal_medical_records_url": _portal_url("patient_portal_medical_records", language),
            "portal_account_url": _portal_url("patient_portal_account", language),
            "portal_password_change_url": _portal_url("patient_portal_password_change", language),
            "portal_account_recovery_url": _portal_url("patient_portal_account_recovery", language),
            "portal_language_switch_url": _portal_language_switch_url(request, language),
            "portal_language_switch_label": "English" if language == "ar" else "العربية",
            "portal_nav_items": [
                {
                    "key": "dashboard",
                    "label": nav_labels["dashboard"],
                    "url": _portal_url("patient_portal_dashboard", language),
                },
                {
                    "key": "appointments",
                    "label": nav_labels["appointments"],
                    "url": _portal_url("patient_portal_appointment_list", language),
                },
                {
                    "key": "book",
                    "label": nav_labels["book"],
                    "url": _booking_start_url(language),
                },
                {
                    "key": "medical_records",
                    "label": nav_labels["medical_records"],
                    "url": _portal_url("patient_portal_medical_records", language),
                },
                {
                    "key": "consultations",
                    "label": nav_labels["consultations"],
                    "url": _portal_url("patient_portal_consultation_list", language),
                },
                {
                    "key": "link",
                    "label": nav_labels["link"],
                    "url": _portal_url("patient_portal_link_appointment", language),
                },
                {
                    "key": "account",
                    "label": nav_labels["account"],
                    "url": _portal_url("patient_portal_account", language),
                },
                {
                    "key": "password",
                    "label": nav_labels["password"],
                    "url": _portal_url("patient_portal_password_change", language),
                },
            ],
            "portal_logout_label": nav_labels["logout"],
            "canonical_url": request.build_absolute_uri(canonical_path),
        }
    )
    context.update(extra)
    return context


def _authenticated_portal_context(request, language, **extra):
    language = _language(language)
    extra.setdefault("portal_closeout", True)
    extra.setdefault("suppress_footer", True)
    extra.setdefault(
        "meta_description",
        (
            "الوصول إلى مواعيدك وسجلك الطبي وحسابك في بوابة المريض."
            if language == "ar"
            else "Access your appointments, medical records, and account in the Patient Portal."
        ),
    )
    return _portal_context(request, language, **extra)


def _login_required(view_func):
    @never_cache
    def wrapped(request, *args, **kwargs):
        language = _language(kwargs.get("language", "ar"))
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                login_url=_login_url_with_query(language, role="patient"),
            )
        return view_func(request, *args, **kwargs)

    return wrapped


def _password_change_form(user, data=None, language="ar"):
    form = PasswordChangeForm(user=user, data=data)
    if _language(language) == "ar":
        form.fields["old_password"].label = "كلمة المرور الحالية"
        form.fields["new_password1"].label = "كلمة المرور الجديدة"
        form.fields["new_password2"].label = "تأكيد كلمة المرور الجديدة"
    else:
        form.fields["old_password"].label = "Current password"
        form.fields["new_password1"].label = "New password"
        form.fields["new_password2"].label = "Confirm new password"
    return form


def _patient_media_response(media):
    if not media.file:
        raise Http404("Media unavailable.")
    if not media.file.storage.exists(media.file.name):
        raise Http404("Media unavailable.")

    response = FileResponse(
        media.file.open("rb"),
        as_attachment=False,
        filename=_patient_media_presentation_filename(media),
        content_type=media.content_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _patient_media_presentation_filename(media):
    source_name = PurePosixPath(str(media.download_filename or "").replace("\\", "/")).name
    extension = PurePosixPath(source_name).suffix.lower()
    return f"patient-media-{media.public_id}{extension}"


@_login_required
def portal_dashboard(request, language="ar"):
    language = _language(language)
    appointment_groups = services.upcoming_and_recent_appointments(request.user, language=language)
    linked_count = services.patient_appointments_queryset(request.user).count()
    return render(
        request,
        "patients/portal_dashboard.html",
        _authenticated_portal_context(
            request,
            language,
            display_name=services.patient_display_name(request.user),
            linked_count=linked_count,
            upcoming_appointments=appointment_groups["upcoming"],
            recent_appointments=appointment_groups["recent"],
            portal_section="dashboard",
        ),
    )


@sensitive_post_parameters("password")
@never_cache
def portal_login(request, language="ar"):
    language = _language(language)
    next_url = _safe_next_url(request)
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect(next_url or _doctor_dashboard_url(language))
        return redirect(_portal_url("patient_portal_dashboard", language))

    requested_role = request.POST.get("role") if request.method == "POST" else request.GET.get("role")
    selected_role = "doctor" if requested_role == "doctor" else "patient"

    patient_form = PatientLoginForm(request=request, language=language)
    doctor_form = StaffLoginForm(request=request, language=language)

    if request.method == "POST":
        if selected_role == "doctor":
            doctor_form = StaffLoginForm(request.POST, request=request, language=language)
            if doctor_form.is_valid():
                auth_login(request, doctor_form.user)
                return redirect(next_url or _doctor_dashboard_url(language))
        else:
            patient_form = PatientLoginForm(request.POST, request=request, language=language)
            normalized_phone = rate_limits.normalized_phone_or_empty(request.POST.get("phone"))
            attempt_limit = rate_limits.check_login_attempt_rate_limit(
                request,
                normalized_phone=normalized_phone,
            )
            form_valid = patient_form.is_valid()
            if not attempt_limit.allowed:
                patient_form.add_error(None, auth_error_message("rate_limit", language))
            elif form_valid:
                auth_login(request, patient_form.user)
                return redirect(next_url or _portal_url("patient_portal_dashboard", language))

    login_url = _login_url(language)
    alternate_language = "en" if language == "ar" else "ar"
    active_form = doctor_form if selected_role == "doctor" else patient_form
    context = _portal_context(request, language)
    clinic_name = context["clinic"]["name_ar" if language == "ar" else "name_en"]
    context.update(
        {
            "page_key": "login",
            "page_title": (
                f"تسجيل الدخول | {clinic_name}" if language == "ar" else f"Sign in | {clinic_name}"
            ),
            "meta_description": (
                "تسجيل دخول آمن للمرضى وأطباء العيادة."
                if language == "ar"
                else "Secure sign in for clinic patients and doctors."
            ),
            "canonical_url": request.build_absolute_uri(login_url),
            "login_url": login_url,
            "portal_login_url": login_url,
            "selected_role": selected_role,
            "patient_form": patient_form,
            "doctor_form": doctor_form,
            "form": active_form,
            "next_url": next_url,
            "patient_role_url": _login_url_with_query(language, role="patient", next_url=next_url),
            "doctor_role_url": _login_url_with_query(language, role="doctor", next_url=next_url),
            "auth_language_url": _login_url_with_query(
                alternate_language,
                role=selected_role,
                next_url=next_url,
            ),
            "phone_countries": INTERNATIONAL_PHONE_COUNTRIES,
        }
    )

    return render(
        request,
        "patients/portal_login.html",
        context,
    )


@sensitive_post_parameters("password1", "password2")
@never_cache
def portal_register(request, language="ar"):
    language = _language(language)
    next_url = _safe_next_url(request)
    if request.user.is_authenticated:
        return redirect(next_url or _portal_url("patient_portal_dashboard", language))

    if request.method == "POST":
        form = PatientRegistrationForm(request.POST, language=language)
        normalized_phone = rate_limits.normalized_phone_or_empty(request.POST.get("phone"))
        attempt_limit = rate_limits.check_registration_attempt_rate_limit(
            request,
            normalized_phone=normalized_phone,
        )
        form_valid = form.is_valid()
        if not attempt_limit.allowed:
            form.add_error(None, auth_error_message("rate_limit", language))
        elif form_valid:
            user = form.save()
            if user is not None:
                auth_login(request, user)
                messages.success(
                    request,
                    "تم إنشاء حساب بوابة المريض."
                    if language == "ar"
                    else "Your patient portal account has been created.",
                )
                return redirect(next_url or _portal_url("patient_portal_dashboard", language))
    else:
        form = PatientRegistrationForm(language=language)

    register_url = _portal_url("patient_portal_register", language)
    alternate_language = "en" if language == "ar" else "ar"
    auth_language_url = _portal_url("patient_portal_register", alternate_language)
    if next_url:
        auth_language_url = f"{auth_language_url}?{urlencode({'next': next_url})}"

    context = _portal_context(request, language, form=form, next_url=next_url)
    clinic_name = context["clinic"]["name_ar" if language == "ar" else "name_en"]
    context.update(
        {
            "page_key": "register",
            "page_title": (
                f"إنشاء حساب | {clinic_name}"
                if language == "ar"
                else f"Create your account | {clinic_name}"
            ),
            "meta_description": (
                "إنشاء حساب المريض في العيادة."
                if language == "ar"
                else "Create your clinic patient account."
            ),
            "canonical_url": request.build_absolute_uri(register_url),
            "auth_language_url": auth_language_url,
            "phone_countries": INTERNATIONAL_PHONE_COUNTRIES,
        }
    )

    return render(
        request,
        "patients/portal_register.html",
        context,
    )


@never_cache
def portal_logout(request, language="ar"):
    language = _language(language)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    auth_logout(request)
    return redirect(_login_url(language))


@_login_required
def portal_account(request, language="ar"):
    language = _language(language)
    linked_count = services.patient_appointments_queryset(request.user).count()
    return render(
        request,
        "patients/account.html",
        _authenticated_portal_context(
            request,
            language,
            display_name=services.patient_display_name(request.user),
            masked_username=services.masked_account_identifier(request.user.username),
            email=request.user.email,
            linked_count=linked_count,
            portal_section="account",
        ),
    )


@sensitive_post_parameters(
    "old_password",
    "new_password1",
    "new_password2",
    "current_password",
    "otp",
)
@_login_required
def portal_password_change(request, language="ar"):
    language = _language(language)
    action = request.POST.get("action", "password") if request.method == "POST" else ""
    form = _password_change_form(request.user, language=language)
    phone_form = AccountPhoneChangeStartForm(user=request.user, language=language)
    verify_form = AccountPhoneChangeVerifyForm(language=language)

    if request.method == "POST" and action == "password":
        form = _password_change_form(request.user, data=request.POST, language=language)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(
                request,
                "تم تغيير كلمة مرور البوابة."
                if language == "ar"
                else "Your portal password has been changed.",
            )
            return redirect(_portal_url("patient_portal_account", language))

    elif request.method == "POST" and action == "phone_start":
        phone_form = AccountPhoneChangeStartForm(
            request.POST,
            user=request.user,
            language=language,
        )
        attempt_limit = rate_limits.check_phone_change_start_rate_limit(request)
        if not attempt_limit.allowed:
            phone_form.add_error(
                None,
                "عدد محاولات التحقق كبير. حاول لاحقًا."
                if language == "ar"
                else "Too many verification requests. Please try again later.",
            )
        elif phone_form.is_valid():
            try:
                phone_change.start_account_phone_change(
                    user=request.user,
                    phone_raw=phone_form.cleaned_data["new_phone"],
                    phone_e164=phone_form.normalized_phone,
                    language=language,
                    propagate_to_upcoming_appointments=phone_form.cleaned_data[
                        "propagate_to_upcoming_appointments"
                    ],
                )
            except WhatsAppOtpServiceUnavailable:
                phone_form.add_error(
                    None,
                    "خدمة التحقق غير متاحة حاليًا. حاول لاحقًا."
                    if language == "ar"
                    else "Verification service is currently unavailable. Please try again later.",
                )
            except phone_change.PhoneChangeConflictError:
                phone_form.add_error(
                    "new_phone",
                    "تعذر استخدام هذا الرقم."
                    if language == "ar"
                    else "This phone cannot be used.",
                )
            else:
                messages.success(
                    request,
                    "تم إرسال رمز التحقق عبر واتساب إلى الرقم الجديد."
                    if language == "ar"
                    else "A WhatsApp verification code was sent to the new phone.",
                )
                return redirect(_portal_url("patient_portal_password_change", language))

    elif request.method == "POST" and action == "phone_verify":
        verify_form = AccountPhoneChangeVerifyForm(request.POST, language=language)
        attempt_limit = rate_limits.check_phone_change_verify_rate_limit(request)
        if not attempt_limit.allowed:
            verify_form.add_error(
                None,
                "عدد محاولات التحقق كبير. حاول لاحقًا."
                if language == "ar"
                else "Too many verification attempts. Please try again later.",
            )
        elif verify_form.is_valid():
            result = phone_change.verify_account_phone_change(
                user=request.user,
                challenge_id=verify_form.cleaned_data["challenge_id"],
                code=verify_form.cleaned_data["otp"],
            )
            if result.succeeded:
                update_session_auth_hash(request, result.user)
                messages.success(
                    request,
                    "تم تغيير رقم حسابك. استخدم الرقم الجديد لتسجيل الدخول."
                    if language == "ar"
                    else "Your account phone was changed. Use the new phone to sign in.",
                )
                return redirect(_portal_url("patient_portal_password_change", language))
            verify_form.add_error(
                "otp" if result.reason in {"invalid", "attempts", "expired"} else None,
                "رمز التحقق غير صالح أو منتهي."
                if language == "ar"
                else "The verification code is invalid or expired.",
            )

    elif request.method == "POST" and action == "phone_resend":
        challenge_id = request.POST.get("challenge_id")
        attempt_limit = rate_limits.check_phone_change_resend_rate_limit(request)
        if not attempt_limit.allowed:
            messages.error(
                request,
                "عدد طلبات إعادة الإرسال كبير. حاول لاحقًا."
                if language == "ar"
                else "Too many resend requests. Please try again later.",
            )
        else:
            try:
                phone_change.resend_account_phone_change(
                    user=request.user,
                    challenge_id=challenge_id,
                    language=language,
                )
            except WhatsAppOtpServiceUnavailable:
                messages.error(
                    request,
                    "خدمة التحقق غير متاحة حاليًا. حاول لاحقًا."
                    if language == "ar"
                    else "Verification service is currently unavailable. Please try again later.",
                )
            except (
                phone_change.PhoneChangeChallengeError,
                phone_change.PhoneChangeConflictError,
                ValidationError,
            ):
                messages.error(
                    request,
                    "تعذر إعادة إرسال الرمز الآن."
                    if language == "ar"
                    else "The code cannot be resent right now.",
                )
            else:
                messages.success(
                    request,
                    "تم إرسال رمز تحقق جديد."
                    if language == "ar"
                    else "A new verification code was sent.",
                )
        return redirect(_portal_url("patient_portal_password_change", language))

    active_challenge = AccountPhoneChangeChallenge.objects.filter(
        user=request.user,
        consumed_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()
    if active_challenge is not None and not verify_form.is_bound:
        verify_form = AccountPhoneChangeVerifyForm(
            initial={"challenge_id": active_challenge.public_id},
            language=language,
        )

    return render(
        request,
        "patients/password_change.html",
        _authenticated_portal_context(
            request,
            language,
            form=form,
            phone_form=phone_form,
            verify_form=verify_form,
            active_challenge=active_challenge,
            masked_account_phone=services.masked_account_identifier(request.user.username),
            phone_countries=INTERNATIONAL_PHONE_COUNTRIES,
            portal_section="password",
        ),
    )


@require_GET
@never_cache
def portal_account_recovery(request, language="ar"):
    language = _language(language)
    recovery_url = _portal_url("patient_portal_account_recovery", language)
    alternate_language = "en" if language == "ar" else "ar"
    context = _portal_context(request, language, portal_section="account_recovery")
    clinic_name = context["clinic"]["name_ar" if language == "ar" else "name_en"]
    context.update(
        {
            "page_key": "account-recovery",
            "page_title": (
                f"استعادة الحساب | {clinic_name}"
                if language == "ar"
                else f"Account recovery | {clinic_name}"
            ),
            "meta_description": (
                "تواصل مع العيادة للتحقق من هويتك واستعادة الوصول إلى حسابك."
                if language == "ar"
                else "Contact the clinic to verify your identity and restore account access."
            ),
            "canonical_url": request.build_absolute_uri(recovery_url),
            "auth_language_url": _portal_url(
                "patient_portal_account_recovery",
                alternate_language,
            ),
        }
    )
    return render(
        request,
        "patients/account_recovery.html",
        context,
    )


@sensitive_post_parameters("public_token", "phone")
@_login_required
def portal_link_appointment(request, language="ar"):
    language = _language(language)
    initial = {"public_token": _token_initial(request)}
    if request.method == "POST":
        form = AppointmentLinkForm(request.POST, language=language)
        form_valid = form.is_valid()
        attempt_limit = rate_limits.check_link_attempt_rate_limit(
            request,
            normalized_phone=form.normalized_phone,
        )
        if not attempt_limit.allowed:
            form.add_error(None, attempt_limit.message)
        elif form_valid:
            try:
                result = services.link_appointment_to_user(
                    user=request.user,
                    public_token=form.token,
                    normalized_phone=form.normalized_phone,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                if result.already_linked:
                    messages.success(
                        request,
                        "هذا الموعد مرتبط ببوابتك بالفعل."
                        if language == "ar"
                        else "This appointment is already linked to your portal.",
                    )
                else:
                    messages.success(
                        request,
                        "تم ربط الموعد ببوابتك."
                        if language == "ar"
                        else "Appointment linked to your portal.",
                    )
                return redirect(
                    _portal_url(
                        "patient_portal_appointment_detail",
                        language,
                        public_token=result.appointment.public_token,
                    )
                )
    else:
        form = AppointmentLinkForm(initial=initial, language=language)

    return render(
        request,
        "patients/link_appointment.html",
        _authenticated_portal_context(
            request,
            language,
            form=form,
            phone_countries=INTERNATIONAL_PHONE_COUNTRIES,
            portal_section="link",
        ),
    )


def _link_recovery_generic_message(language):
    return (
        "تعذر استعادة المواعيد تلقائيًا. تواصل مع العيادة لدعم الحساب."
        if language == "ar"
        else "Appointments cannot be recovered automatically. Contact the clinic for account support."
    )


@sensitive_post_parameters("phone", "otp")
@_login_required
@never_cache
def portal_link_appointment_recovery(request, language="ar"):
    language = _language(language)
    action = request.POST.get("action", "") if request.method == "POST" else ""
    start_form = AppointmentLinkRecoveryStartForm(language=language)
    verify_form = AppointmentLinkRecoveryVerifyForm(language=language)

    if request.method == "POST" and action == "start":
        start_form = AppointmentLinkRecoveryStartForm(request.POST, language=language)
        form_valid = start_form.is_valid()
        attempt_limit = rate_limits.check_link_recovery_start_rate_limit(
            request,
            normalized_phone=start_form.normalized_phone,
        )
        if not attempt_limit.allowed:
            start_form.add_error(
                None,
                "عدد محاولات التحقق كبير. حاول لاحقًا."
                if language == "ar"
                else "Too many verification requests. Please try again later.",
            )
        elif form_valid:
            try:
                link_recovery.start_appointment_link_recovery(
                    user=request.user,
                    phone_raw=start_form.cleaned_data["phone"],
                    phone_e164=start_form.normalized_phone,
                    language=language,
                )
            except WhatsAppOtpServiceUnavailable:
                start_form.add_error(
                    None,
                    "خدمة التحقق غير متاحة حاليًا. حاول لاحقًا."
                    if language == "ar"
                    else "Verification service is currently unavailable. Please try again later.",
                )
            else:
                request.session.pop(_LINK_RECOVERY_SESSION_KEY, None)
                messages.success(
                    request,
                    "تم إرسال رمز تحقق من 6 أرقام عبر واتساب."
                    if language == "ar"
                    else "A 6-digit verification code was sent by WhatsApp.",
                )
                return redirect(
                    _portal_url("patient_portal_link_appointment_recovery", language)
                )

    elif request.method == "POST" and action == "verify":
        submitted_form = AppointmentLinkRecoveryVerifyForm(request.POST, language=language)
        attempt_limit = rate_limits.check_link_recovery_verify_rate_limit(request)
        challenge_id = request.POST.get("challenge_id")
        error_message = ""
        if not attempt_limit.allowed:
            error_message = (
                "عدد محاولات التحقق كبير. حاول لاحقًا."
                if language == "ar"
                else "Too many verification attempts. Please try again later."
            )
        elif not submitted_form.is_valid():
            error_message = (
                "رمز التحقق غير صالح أو منتهي."
                if language == "ar"
                else "The verification code is invalid or expired."
            )
        else:
            result = link_recovery.verify_appointment_link_recovery(
                user=request.user,
                challenge_id=submitted_form.cleaned_data["challenge_id"],
                code=submitted_form.cleaned_data["otp"],
            )
            if result.succeeded:
                request.session[_LINK_RECOVERY_SESSION_KEY] = str(result.challenge.public_id)
                return redirect(
                    _portal_url("patient_portal_link_appointment_recovery", language)
                )
            error_message = (
                "رمز التحقق غير صالح أو منتهي."
                if language == "ar"
                else "The verification code is invalid or expired."
            )
        # Never re-render a submitted OTP value.
        verify_form = AppointmentLinkRecoveryVerifyForm(
            {"challenge_id": challenge_id, "otp": ""},
            language=language,
        )
        verify_form.is_valid()
        verify_form._errors.pop("otp", None)
        verify_form.add_error("otp", error_message)

    elif request.method == "POST" and action == "resend":
        challenge_id = request.POST.get("challenge_id")
        attempt_limit = rate_limits.check_link_recovery_resend_rate_limit(request)
        if not attempt_limit.allowed:
            messages.error(
                request,
                "عدد طلبات إعادة الإرسال كبير. حاول لاحقًا."
                if language == "ar"
                else "Too many resend requests. Please try again later.",
            )
        else:
            try:
                link_recovery.resend_appointment_link_recovery(
                    user=request.user,
                    challenge_id=challenge_id,
                    language=language,
                )
            except WhatsAppOtpServiceUnavailable:
                messages.error(
                    request,
                    "خدمة التحقق غير متاحة حاليًا. حاول لاحقًا."
                    if language == "ar"
                    else "Verification service is currently unavailable. Please try again later.",
                )
            except (link_recovery.LinkRecoveryChallengeError, ValidationError):
                messages.error(
                    request,
                    "تعذر إعادة إرسال الرمز الآن."
                    if language == "ar"
                    else "The code cannot be resent right now.",
                )
            else:
                messages.success(
                    request,
                    "تم إرسال رمز تحقق جديد."
                    if language == "ar"
                    else "A new verification code was sent.",
                )
        return redirect(_portal_url("patient_portal_link_appointment_recovery", language))

    elif request.method == "POST" and action == "link":
        challenge_id = request.session.get(_LINK_RECOVERY_SESSION_KEY)
        if not challenge_id:
            messages.error(request, _link_recovery_generic_message(language))
        else:
            try:
                link_recovery.link_verified_recovery_patient(
                    user=request.user,
                    challenge_id=challenge_id,
                )
            except (
                link_recovery.LinkRecoveryChallengeError,
                link_recovery.LinkRecoveryConflictError,
                ValidationError,
            ):
                messages.error(request, _link_recovery_generic_message(language))
            else:
                request.session.pop(_LINK_RECOVERY_SESSION_KEY, None)
                messages.success(
                    request,
                    "تم ربط هذه المواعيد بحسابك."
                    if language == "ar"
                    else "These appointments were linked to your account.",
                )
                return redirect(_portal_url("patient_portal_appointment_list", language))
        return redirect(_portal_url("patient_portal_link_appointment_recovery", language))

    active_challenge = AppointmentLinkRecoveryChallenge.objects.filter(
        user=request.user,
        consumed_at__isnull=True,
        verified_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at", "-id").first()
    if active_challenge is not None and not verify_form.is_bound:
        verify_form = AppointmentLinkRecoveryVerifyForm(
            initial={"challenge_id": active_challenge.public_id},
            language=language,
        )

    recovery_candidates = None
    verified_challenge_id = request.session.get(_LINK_RECOVERY_SESSION_KEY)
    if verified_challenge_id:
        try:
            recovery_candidates = link_recovery.get_verified_recovery_candidates(
                user=request.user,
                challenge_id=verified_challenge_id,
            )
        except link_recovery.LinkRecoveryChallengeError:
            request.session.pop(_LINK_RECOVERY_SESSION_KEY, None)
        else:
            for appointment in recovery_candidates.appointments:
                appointment.portal_status_label = services.patient_status_label(
                    appointment.status,
                    language,
                )

    return render(
        request,
        "patients/link_appointment_recovery.html",
        _authenticated_portal_context(
            request,
            language,
            start_form=start_form,
            verify_form=verify_form,
            active_challenge=active_challenge,
            recovery_candidates=recovery_candidates,
            recovery_generic_message=_link_recovery_generic_message(language),
            phone_countries=INTERNATIONAL_PHONE_COUNTRIES,
            portal_section="link",
        ),
    )


@require_GET
@_login_required
def portal_book_appointment(request, language="ar"):
    return redirect(_booking_start_url(language))


def _consultation_status_label(status, language):
    labels = {
        Consultation.Status.NEW: {"ar": "جديدة", "en": "New"},
        Consultation.Status.ANSWERED: {"ar": "تم الرد", "en": "Answered"},
        Consultation.Status.CLOSED: {"ar": "مغلقة", "en": "Closed"},
    }
    return labels.get(status, {"ar": status, "en": status})[language]


@require_GET
@_login_required
def portal_consultation_list(request, language="ar"):
    language = _language(language)
    consultations = list(
        Consultation.objects.filter(patient__user=request.user)
        .select_related("patient")
        .prefetch_related("attachments")
    )
    for consultation in consultations:
        consultation.portal_status_label = _consultation_status_label(consultation.status, language)
    return render(
        request,
        "patients/consultation_list.html",
        _authenticated_portal_context(
            request,
            language,
            consultations=consultations,
            portal_section="consultations",
        ),
    )


@sensitive_post_parameters()
@_login_required
def portal_consultation_new(request, language="ar"):
    language = _language(language)
    if request.method == "POST":
        form = ConsultationCreateForm(request.POST, request.FILES, language=language)
        attempt_limit = rate_limits.check_consultation_submission_rate_limit(request)
        if not attempt_limit.allowed:
            form.is_valid()
            form.add_error(
                None,
                "عدد طلبات الاستشارة كبير. حاول لاحقًا."
                if language == "ar"
                else "Too many consultation submissions. Please try again later.",
            )
        elif form.is_valid():
            try:
                consultation = consultation_services.create_consultation(
                    user=request.user,
                    question=form.cleaned_data["question"],
                    uploaded_files=form.cleaned_data["attachments"],
                )
            except PatientProfileConflictError:
                form.add_error(
                    None,
                    "يوجد سجل يحتاج إلى الربط الآمن أولًا. استخدم ربط موعد أو تواصل مع العيادة."
                    if language == "ar"
                    else "An existing record must be securely linked first. Use Link Appointment or contact the clinic.",
                )
            except (ValidationError, ValueError):
                form.add_error(
                    "attachments",
                    "تعذر حفظ المرفقات. راجع الملفات وحاول مرة أخرى."
                    if language == "ar"
                    else "The attachments could not be saved. Review the files and try again.",
                )
            else:
                messages.success(
                    request,
                    "تم إرسال الاستشارة."
                    if language == "ar"
                    else "Your consultation was submitted.",
                )
                return redirect(
                    _portal_url(
                        "patient_portal_consultation_detail",
                        language,
                        public_id=consultation.public_id,
                    )
                )
    else:
        form = ConsultationCreateForm(language=language)
    return render(
        request,
        "patients/consultation_new.html",
        _authenticated_portal_context(
            request,
            language,
            form=form,
            portal_section="consultations",
        ),
    )


@require_GET
@_login_required
def portal_consultation_detail(request, public_id, language="ar"):
    language = _language(language)
    consultation = get_object_or_404(
        Consultation.objects.select_related(
            "patient", "replied_by", "audio_reply"
        ).prefetch_related("attachments"),
        public_id=public_id,
        patient__user=request.user,
    )
    return render(
        request,
        "patients/consultation_detail.html",
        _authenticated_portal_context(
            request,
            language,
            consultation=consultation,
            status_label=_consultation_status_label(consultation.status, language),
            can_delete_consultation=consultation_services.patient_can_delete_consultation(
                consultation,
                request.user,
            ),
            consultation_delete_url=_portal_url(
                "patient_portal_consultation_delete",
                language,
                public_id=consultation.public_id,
            ),
            portal_section="consultations",
        ),
    )


@require_http_methods(["GET", "POST"])
@_login_required
def portal_consultation_delete(request, public_id, language="ar"):
    language = _language(language)
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient"),
        public_id=public_id,
        patient__user=request.user,
    )
    if request.method == "GET":
        if not consultation_services.patient_can_delete_consultation(
            consultation,
            request.user,
        ):
            raise Http404("Consultation cannot be deleted.")
        return render(
            request,
            "patients/consultation_confirm_delete.html",
            _authenticated_portal_context(
                request,
                language,
                consultation=consultation,
                consultation_delete_url=_portal_url(
                    "patient_portal_consultation_delete",
                    language,
                    public_id=consultation.public_id,
                ),
                consultation_detail_url=_portal_url(
                    "patient_portal_consultation_detail",
                    language,
                    public_id=consultation.public_id,
                ),
                portal_section="consultations",
            ),
        )

    try:
        consultation_services.delete_unhandled_consultation(
            user=request.user,
            public_id=public_id,
        )
    except consultation_services.ConsultationDeleteError:
        messages.error(
            request,
            "تعذر حذف الاستشارة بأمان. لم يتم تغييرها."
            if language == "ar"
            else "The consultation could not be deleted safely and was not changed.",
        )
        return redirect(
            _portal_url(
                "patient_portal_consultation_detail",
                language,
                public_id=public_id,
            )
        )
    messages.success(
        request,
        "تم حذف الاستشارة."
        if language == "ar"
        else "The consultation was deleted.",
    )
    return redirect(_portal_url("patient_portal_consultation_list", language))


def _consultation_attachment_response(attachment):
    if not attachment.file_exists:
        raise Http404("Attachment unavailable.")
    try:
        file_handle = attachment.file.open("rb")
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise Http404("Attachment unavailable.") from exc
    response = FileResponse(
        file_handle,
        as_attachment=False,
        filename=attachment.presentation_filename,
        content_type=attachment.content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
@_login_required
def portal_consultation_attachment(request, public_id, language="ar"):
    attachment = get_object_or_404(
        ConsultationAttachment.objects.select_related("consultation", "consultation__patient"),
        public_id=public_id,
        consultation__patient__user=request.user,
    )
    return _consultation_attachment_response(attachment)


@require_GET
@_login_required
def portal_consultation_audio_reply(request, public_id, language="ar"):
    audio_reply = get_object_or_404(
        ConsultationAudioReply.objects.select_related(
            "consultation", "consultation__patient"
        ),
        public_id=public_id,
        consultation__patient__user=request.user,
    )
    if not audio_reply.file_exists:
        raise Http404("Audio reply unavailable.")
    try:
        file_handle = audio_reply.file.open("rb")
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise Http404("Audio reply unavailable.") from exc
    response = FileResponse(
        file_handle,
        as_attachment=False,
        filename=audio_reply.presentation_filename,
        content_type=audio_reply.content_type,
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@_login_required
def portal_appointment_list(request, language="ar"):
    language = _language(language)
    appointments = services.portal_appointments(request.user, language=language)
    return render(
        request,
        "patients/appointment_list.html",
        _authenticated_portal_context(
            request,
            language,
            appointments=appointments,
            portal_section="appointments",
        ),
    )


@require_GET
@_login_required
def patient_portal_medical_records(request, language="ar"):
    language = _language(language)
    patient = services.user_patient_profile(request.user)
    visits = []
    notes = []
    media_items = []

    if patient is not None:
        visits = (
            VisitRecord.objects.filter(patient=patient, is_visible_to_patient=True)
            .select_related("appointment", "appointment__doctor", "appointment__visit_type")
            .order_by("-visit_date", "-created_at")
        )
        notes = list(
            ClinicalNote.objects.filter(patient=patient, is_visible_to_patient=True)
            .select_related("visit")
            .order_by("-created_at")
        )
        for note in notes:
            note.portal_type_label = _portal_note_type_label(note.note_type, language)
        visible_media = (
            RecordMedia.objects.filter(
                patient=patient,
                visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
                is_active=True,
                trashed_at__isnull=True,
            )
            .select_related("visit")
            .order_by("-uploaded_at")
        )
        media_items = [
            {
                "media": media,
                "media_type_label": _portal_media_type_label(media.media_type, language),
                "media_url": _portal_url(
                    "patient_portal_medical_record_media_download",
                    language,
                    public_id=media.public_id,
                ),
            }
            for media in visible_media
        ]

    return render(
        request,
        "patients/medical_records.html",
        _authenticated_portal_context(
            request,
            language,
            patient=patient,
            visits=visits,
            notes=notes,
            media_items=media_items,
            portal_section="medical_records",
        ),
    )


@require_GET
@_login_required
def patient_portal_medical_record_media_download(request, public_id, language="ar"):
    patient = services.user_patient_profile(request.user)
    if patient is None:
        raise Http404("Media unavailable.")

    try:
        media = RecordMedia.objects.select_related("patient", "visit").get(
            public_id=public_id,
            patient=patient,
            visibility=RecordMedia.Visibility.VISIBLE_TO_PATIENT,
            is_active=True,
            trashed_at__isnull=True,
        )
    except RecordMedia.DoesNotExist as exc:
        raise Http404("Media unavailable.") from exc

    return _patient_media_response(media)


@_login_required
def portal_appointment_detail(request, public_token, language="ar"):
    language = _language(language)
    appointment = get_object_or_404(
        Appointment.objects.select_related("doctor", "patient", "visit_type"),
        public_token=public_token,
        patient__user=request.user,
    )
    cutoff_minutes = booking_services.get_booking_settings().patient_cancellation_cutoff_minutes
    return render(
        request,
        "patients/appointment_detail.html",
        _authenticated_portal_context(
            request,
            language,
            appointment=appointment,
            status_label=services.patient_status_label(appointment.status, language),
            can_cancel_appointment=booking_operations.patient_can_cancel_appointment(
                appointment,
                request.user,
                cutoff_minutes=cutoff_minutes,
            ),
            appointment_cancel_url=_portal_url(
                "patient_portal_appointment_cancel",
                language,
                reference=_appointment_cancellation_reference(appointment),
            ),
            patient_cancellation_cutoff_hours=cutoff_minutes // 60,
            portal_section="appointments",
        ),
    )


@require_http_methods(["GET", "POST"])
@_login_required
def portal_appointment_cancel(request, reference, language="ar"):
    language = _language(language)
    appointment = _appointment_from_cancellation_reference(reference, request.user)
    cutoff_minutes = booking_services.get_booking_settings().patient_cancellation_cutoff_minutes
    if request.method == "GET":
        if not booking_operations.patient_can_cancel_appointment(
            appointment,
            request.user,
            cutoff_minutes=cutoff_minutes,
        ):
            raise Http404("Appointment cannot be cancelled.")
        return render(
            request,
            "patients/appointment_confirm_cancel.html",
            _authenticated_portal_context(
                request,
                language,
                appointment=appointment,
                appointment_cancel_url=_portal_url(
                    "patient_portal_appointment_cancel",
                    language,
                    reference=reference,
                ),
                appointment_detail_url=_portal_url(
                    "patient_portal_appointment_detail",
                    language,
                    public_token=appointment.public_token,
                ),
                patient_cancellation_cutoff_hours=cutoff_minutes // 60,
                portal_section="appointments",
            ),
        )

    try:
        booking_operations.patient_cancel_appointment(
            public_token=appointment.public_token,
            user=request.user,
        )
    except ValidationError:
        messages.error(
            request,
            "تعذر إلغاء الموعد. قد تكون حالته أو مهلة الإلغاء قد تغيرت."
            if language == "ar"
            else "The appointment could not be cancelled. Its status or cancellation window may have changed.",
        )
    else:
        messages.success(
            request,
            "تم إلغاء الموعد." if language == "ar" else "The appointment was cancelled.",
        )
    return redirect(
        _portal_url(
            "patient_portal_appointment_detail",
            language,
            public_token=appointment.public_token,
        )
    )
