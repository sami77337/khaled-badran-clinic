from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET

from apps.booking.models import Appointment
from apps.core.views import _base_context
from apps.patients import rate_limits, services
from apps.patients.forms import AppointmentLinkForm, PatientLoginForm, PatientRegistrationForm


def _language(language):
    return "en" if language == "en" else "ar"


def _route_name(name, language):
    return f"{name}_en" if _language(language) == "en" else name


def _portal_url(name, language, **kwargs):
    return reverse(_route_name(name, language), kwargs=kwargs or None)


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


def _portal_context(request, language, **extra):
    language = _language(language)
    context = _base_context(request, "patient_portal", language)
    nav_labels = {
        "ar": {
            "dashboard": "لوحة البوابة",
            "appointments": "المواعيد",
            "link": "ربط موعد",
            "account": "الحساب",
            "password": "تغيير كلمة المرور",
            "logout": "تسجيل الخروج",
        },
        "en": {
            "dashboard": "Dashboard",
            "appointments": "Appointments",
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
            "portal_login_url": _portal_url("patient_portal_login", language),
            "portal_logout_url": _portal_url("patient_portal_logout", language),
            "portal_register_url": _portal_url("patient_portal_register", language),
            "portal_link_url": _portal_url("patient_portal_link_appointment", language),
            "portal_appointments_url": _portal_url("patient_portal_appointment_list", language),
            "portal_account_url": _portal_url("patient_portal_account", language),
            "portal_password_change_url": _portal_url("patient_portal_password_change", language),
            "portal_account_recovery_url": _portal_url("patient_portal_account_recovery", language),
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
            "canonical_url": request.build_absolute_uri(_portal_url("patient_portal_dashboard", language)),
        }
    )
    context.update(extra)
    return context


def _login_required(view_func):
    @never_cache
    def wrapped(request, *args, **kwargs):
        language = _language(kwargs.get("language", "ar"))
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                login_url=_portal_url("patient_portal_login", language),
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


@_login_required
def portal_dashboard(request, language="ar"):
    language = _language(language)
    appointment_groups = services.upcoming_and_recent_appointments(request.user, language=language)
    linked_count = services.patient_appointments_queryset(request.user).count()
    return render(
        request,
        "patients/portal_dashboard.html",
        _portal_context(
            request,
            language,
            display_name=services.patient_display_name(request.user),
            linked_count=linked_count,
            upcoming_appointments=appointment_groups["upcoming"],
            recent_appointments=appointment_groups["recent"],
        ),
    )


@sensitive_post_parameters("password")
@never_cache
def portal_login(request, language="ar"):
    language = _language(language)
    next_url = _safe_next_url(request)
    if request.user.is_authenticated:
        return redirect(next_url or _portal_url("patient_portal_dashboard", language))

    if request.method == "POST":
        form = PatientLoginForm(request.POST, request=request, language=language)
        normalized_phone = rate_limits.normalized_phone_or_empty(request.POST.get("phone"))
        attempt_limit = rate_limits.check_login_attempt_rate_limit(
            request,
            normalized_phone=normalized_phone,
        )
        form_valid = form.is_valid()
        if not attempt_limit.allowed:
            form.add_error(None, attempt_limit.message)
        elif form_valid:
            auth_login(request, form.user)
            return redirect(next_url or _portal_url("patient_portal_dashboard", language))
    else:
        form = PatientLoginForm(request=request, language=language)

    return render(
        request,
        "patients/portal_login.html",
        _portal_context(request, language, form=form, next_url=next_url),
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
            form.add_error(None, attempt_limit.message)
        elif form_valid:
            user = form.save()
            auth_login(request, user)
            messages.success(request, "Your patient portal account has been created.")
            return redirect(next_url or _portal_url("patient_portal_dashboard", language))
    else:
        form = PatientRegistrationForm(language=language)

    return render(
        request,
        "patients/portal_register.html",
        _portal_context(request, language, form=form, next_url=next_url),
    )


@never_cache
def portal_logout(request, language="ar"):
    language = _language(language)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    auth_logout(request)
    return redirect(_portal_url("patient_portal_login", language))


@_login_required
def portal_account(request, language="ar"):
    language = _language(language)
    linked_count = services.patient_appointments_queryset(request.user).count()
    return render(
        request,
        "patients/account.html",
        _portal_context(
            request,
            language,
            display_name=services.patient_display_name(request.user),
            masked_username=services.masked_account_identifier(request.user.username),
            email=request.user.email,
            linked_count=linked_count,
            portal_section="account",
        ),
    )


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@_login_required
def portal_password_change(request, language="ar"):
    language = _language(language)
    if request.method == "POST":
        form = _password_change_form(request.user, data=request.POST, language=language)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your portal password has been changed.")
            return redirect(_portal_url("patient_portal_account", language))
    else:
        form = _password_change_form(request.user, language=language)

    return render(
        request,
        "patients/password_change.html",
        _portal_context(request, language, form=form, portal_section="password"),
    )


@require_GET
@never_cache
def portal_account_recovery(request, language="ar"):
    language = _language(language)
    return render(
        request,
        "patients/account_recovery.html",
        _portal_context(request, language, portal_section="account_recovery"),
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
                    messages.success(request, "This appointment is already linked to your portal.")
                else:
                    messages.success(request, "Appointment linked to your portal.")
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
        _portal_context(request, language, form=form),
    )


@_login_required
def portal_appointment_list(request, language="ar"):
    language = _language(language)
    appointments = services.portal_appointments(request.user, language=language)
    return render(
        request,
        "patients/appointment_list.html",
        _portal_context(request, language, appointments=appointments),
    )


@_login_required
def portal_appointment_detail(request, public_token, language="ar"):
    language = _language(language)
    appointment = get_object_or_404(
        Appointment.objects.select_related("doctor", "patient", "visit_type"),
        public_token=public_token,
        patient__user=request.user,
    )
    return render(
        request,
        "patients/appointment_detail.html",
        _portal_context(
            request,
            language,
            appointment=appointment,
            status_label=services.patient_status_label(appointment.status, language),
        ),
    )
