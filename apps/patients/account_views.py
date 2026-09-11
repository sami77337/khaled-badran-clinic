"""Explicit AR/EN account views; the same OTP requirement applies in every environment."""

from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from apps.booking.phone import normalize_phone
from . import account_otp as otp, rate_limits
from .forms import (
    PatientRegistrationForm,
    auth_error_message,
    _localized_password_error,
)
from .localization import use_page_language


def _language(value):
    return "en" if value == "en" else "ar"


def _mask_phone(value):
    return "••••" + value[-4:]


def _registration_context(
    request, language, *, form=None, otp_stage=False, masked_phone=""
):
    from apps.patients import views as patient_views

    language = _language(language)
    next_url = patient_views._safe_next_url(request)
    context = patient_views._portal_context(
        request, language, form=form, next_url=next_url
    )
    clinic_name = context["clinic"]["name_ar" if language == "ar" else "name_en"]
    register_url = patient_views._portal_url("patient_portal_register", language)
    alternate_language = "en" if language == "ar" else "ar"
    auth_language_url = patient_views._portal_url(
        "patient_portal_register", alternate_language
    )
    if next_url:
        auth_language_url = f"{auth_language_url}?{urlencode({'next': next_url})}"
    context.update(
        {
            "page_key": "register",
            "page_title": (
                f"إنشاء حساب | {clinic_name}"
                if language == "ar"
                else f"Create your account | {clinic_name}"
            ),
            "meta_description": (
                "إنشاء حساب المريض والتحقق من رقم الهاتف."
                if language == "ar"
                else "Create a patient account and verify the phone number."
            ),
            "canonical_url": request.build_absolute_uri(register_url),
            "auth_language_url": auth_language_url,
            "phone_countries": patient_views.INTERNATIONAL_PHONE_COUNTRIES,
            "otp_stage": otp_stage,
            "masked_phone": masked_phone,
        }
    )
    return context


def _recovery_context(request, language, *, stage="start", form=None, masked_phone=""):
    from apps.patients import views as patient_views

    language = _language(language)
    recovery_url = patient_views._portal_url(
        "patient_portal_account_recovery", language
    )
    alternate_language = "en" if language == "ar" else "ar"
    context = patient_views._portal_context(
        request,
        language,
        portal_section="account_recovery",
    )
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
                "استعادة حساب المريض عبر رقم الهاتف ورمز تحقق لمرة واحدة."
                if language == "ar"
                else "Recover a patient account with the phone number and a one-time verification code."
            ),
            "canonical_url": request.build_absolute_uri(recovery_url),
            "auth_language_url": patient_views._portal_url(
                "patient_portal_account_recovery", alternate_language
            ),
            "portal_login_url": patient_views._login_url(language),
            "recovery_stage": stage,
            "form": form,
            "masked_phone": masked_phone,
        }
    )
    return context


class AccountRecoveryStartForm(forms.Form):
    phone = forms.CharField(
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "tel",
                "dir": "ltr",
                "inputmode": "tel",
                "placeholder": "+9627XXXXXXXX",
            }
        ),
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = _language(language)
        self.normalized_phone = ""
        self.fields["phone"].label = (
            "رقم الهاتف" if self.language == "ar" else "Phone number"
        )

    def clean_phone(self):
        raw = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw)
        except ValidationError as exc:
            raise ValidationError(
                auth_error_message("phone_invalid", self.language)
            ) from exc
        return raw.strip()


class OtpVerifyForm(forms.Form):
    otp = forms.CharField(
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "dir": "ltr",
                "inputmode": "numeric",
                "pattern": "[0-9]{6}",
                "placeholder": "000000",
            }
        ),
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = _language(language)
        self.fields["otp"].label = (
            "رمز التحقق" if self.language == "ar" else "Verification code"
        )

    def clean_otp(self):
        value = (self.cleaned_data.get("otp") or "").strip()
        if not otp.OTP_RE.fullmatch(value):
            raise ValidationError(
                "أدخل رمز التحقق المكوّن من 6 أرقام."
                if self.language == "ar"
                else "Enter the 6-digit verification code."
            )
        return value


def _localized_set_password_form(user, data, language):
    form = SetPasswordForm(user=user, data=data)
    for name, field in form.fields.items():
        field.widget.attrs.update(dir="ltr", autocomplete="new-password")
        if language == "ar":
            field.label = (
                "كلمة المرور الجديدة"
                if name == "new_password1"
                else "تأكيد كلمة المرور الجديدة"
            )
            field.error_messages["required"] = auth_error_message(
                "password_required", language
            )
    if data is not None:
        form.is_valid()
        if language == "ar":
            for name, errors in form.errors.as_data().items():
                form.errors[name] = form.error_class(
                    [
                        auth_error_message("password_mismatch", language)
                        if error.code == "password_mismatch"
                        else _localized_password_error(error, language)
                        for error in errors
                    ]
                )
    return form


def _notice(language):
    return (
        "إذا أمكن متابعة الطلب، سيصلك رمز تحقق عبر واتساب."
        if language == "ar"
        else "If the request can proceed, a verification code will arrive by WhatsApp."
    )


def _invalid(language):
    return (
        "رمز التحقق غير صالح أو منتهي."
        if language == "ar"
        else "The verification code is invalid or expired."
    )


def _resend_response(request, purpose, language, url):
    result = otp.resend(request, purpose)
    if result == "cooldown":
        text = (
            "انتظر قليلًا قبل طلب رمز جديد."
            if language == "ar"
            else "Wait briefly before requesting a new code."
        )
    elif result == "limited":
        text = auth_error_message("rate_limit", language)
    else:
        text = _notice(language)
    messages.info(request, text)
    return redirect(url + "?verify=1")


@sensitive_post_parameters("password1", "password2", "otp")
@never_cache
@require_http_methods(["GET", "POST"])
@use_page_language
def portal_register(request, language="ar"):
    from . import views

    url = views._portal_url("patient_portal_register", language)
    if request.user.is_authenticated:
        return redirect(
            views._safe_next_url(request)
            or views._portal_url("patient_portal_dashboard", language)
        )
    action = request.POST.get("action", "start") if request.method == "POST" else ""
    if request.GET.get("verify") == "1" or action in {"verify", "resend"}:
        challenge = otp.challenge_for(request, "registration")
        if not otp.available(challenge):
            messages.error(request, _invalid(language))
            return redirect(url)
        if action == "resend":
            return _resend_response(request, "registration", language, url)
        form = OtpVerifyForm(
            request.POST if request.method == "POST" else None, language=language
        )
        if request.method == "POST":
            form.is_valid()
            allowed = otp.allow_request(
                request, scope="verify", phone=challenge.phone_e164
            )
            result = (
                otp.verify(request, "registration", form.cleaned_data.get("otp", ""))
                if allowed
                else None
            )
            if result:
                user, next_url = result
                auth_login(request, user)
                return redirect(
                    next_url or views._portal_url("patient_portal_dashboard", language)
                )
            form.add_error(
                None,
                _invalid(language)
                if allowed
                else auth_error_message("rate_limit", language),
            )
        context = _registration_context(
            request,
            language,
            form=form,
            otp_stage=True,
            masked_phone=_mask_phone(challenge.phone_e164),
        )
        context["auth_language_url"] += (
            "&verify=1" if "?" in context["auth_language_url"] else "?verify=1"
        )
        return render(request, "patients/account_otp_verify.html", context)

    form = PatientRegistrationForm(
        request.POST if request.method == "POST" else None, language=language
    )
    if request.method == "POST":
        phone = rate_limits.normalized_phone_or_empty(request.POST.get("phone"))
        allowed = otp.registration_allowed(request, phone)
        valid = form.is_valid()
        if not allowed:
            form.add_error(None, auth_error_message("rate_limit", language))
        elif valid:
            if otp.allow_request(request, scope="send", phone=phone, limit=6):
                otp.start(
                    request,
                    "registration",
                    phone,
                    language,
                    registration={
                        "full_name": form.cleaned_data["full_name"],
                        "email": form.cleaned_data.get("email") or "",
                        "password_hash": make_password(form.cleaned_data["password1"]),
                        "next_url": views._safe_next_url(request),
                    },
                )
                return redirect(url + "?verify=1")
            form.add_error(None, auth_error_message("rate_limit", language))
    return render(
        request,
        "patients/portal_register.html",
        _registration_context(request, language, form=form),
    )


@sensitive_post_parameters("otp", "new_password1", "new_password2")
@never_cache
@require_http_methods(["GET", "POST"])
@use_page_language
def portal_account_recovery(request, language="ar"):
    from . import views

    url = views._portal_url("patient_portal_account_recovery", language)
    action = request.POST.get("action", "start") if request.method == "POST" else ""
    challenge = otp.challenge_for(request, "recovery")
    stage = "start"
    if request.GET.get("reset") == "1" or action == "reset":
        stage = "reset"
        user = otp.recovery_user(challenge)
        if user is None:
            messages.error(request, _invalid(language))
            return redirect(url)
        form = _localized_set_password_form(user, None, language)
        if request.method == "POST":
            if otp.allow_request(request, scope="reset", phone=challenge.phone_e164):
                form, succeeded = otp.reset_password(
                    request, request.POST, _localized_set_password_form, language
                )
                if succeeded:
                    messages.success(
                        request,
                        "تم تغيير كلمة المرور. يمكنك تسجيل الدخول الآن."
                        if language == "ar"
                        else "Your password was changed. You can sign in now.",
                    )
                    return redirect(views._login_url(language))
                if form is None:
                    return redirect(url)
            else:
                form = _localized_set_password_form(user, request.POST, language)
                form.add_error(None, auth_error_message("rate_limit", language))
    elif request.GET.get("verify") == "1" or action in {"verify", "resend"}:
        stage = "verify"
        if not otp.available(challenge):
            messages.error(request, _invalid(language))
            return redirect(url)
        if action == "resend":
            return _resend_response(request, "recovery", language, url)
        form = OtpVerifyForm(
            request.POST if request.method == "POST" else None, language=language
        )
        if request.method == "POST":
            form.is_valid()
            allowed = otp.allow_request(
                request, scope="verify", phone=challenge.phone_e164
            )
            user = (
                otp.verify(request, "recovery", form.cleaned_data.get("otp", ""))
                if allowed
                else None
            )
            if user:
                return redirect(url + "?reset=1")
            form.add_error(
                None,
                _invalid(language)
                if allowed
                else auth_error_message("rate_limit", language),
            )
    else:
        form = AccountRecoveryStartForm(
            request.POST if request.method == "POST" else None, language=language
        )
        if request.method == "POST":
            phone = rate_limits.normalized_phone_or_empty(request.POST.get("phone"))
            allowed = otp.allow_request(request, scope="send", phone=phone, limit=6)
            valid = form.is_valid()
            if not allowed:
                form.add_error(None, auth_error_message("rate_limit", language))
            elif valid:
                otp.start(request, "recovery", phone, language)
                messages.info(request, _notice(language))
                return redirect(url + "?verify=1")
    context = _recovery_context(
        request,
        language,
        stage=stage,
        form=form,
        masked_phone=_mask_phone(challenge.phone_e164) if challenge else "",
    )
    if stage != "start":
        context["auth_language_url"] += f"?{stage}=1"
    return render(request, "patients/account_recovery.html", context)
