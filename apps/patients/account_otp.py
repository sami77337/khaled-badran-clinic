"""Production patient-account OTP flows.

The public route names stay unchanged. ``PatientsConfig.ready`` keeps references to
legacy views for local/test compatibility and routes production registration and
recovery through these handlers.
"""

import hashlib
import re
import secrets
import time
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from apps.booking.phone import normalize_phone
from apps.patients.forms import PatientRegistrationForm, auth_error_message
from apps.patients.otp import (
    WhatsAppOtpServiceUnavailable,
    generate_otp_code,
    send_patient_account_otp,
)
from apps.patients import rate_limits


OTP_TTL_SECONDS = 10 * 60
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
RECOVERY_GRANT_TTL_SECONDS = 10 * 60

REGISTRATION_SESSION_KEY = "patient_registration_otp_challenge"
RECOVERY_SESSION_KEY = "patient_recovery_otp_challenge"
RECOVERY_GRANT_SESSION_KEY = "patient_recovery_password_grant"

OTP_RE = re.compile(r"^[0-9]{6}$")


def _language(value):
    return "en" if value == "en" else "ar"


def _otp_required():
    return bool(
        getattr(settings, "PRODUCTION", False)
        or getattr(settings, "PATIENT_ACCOUNT_OTP_REQUIRED", False)
    )


def _challenge_key(token):
    return f"patient-account-otp:{token}"


def _grant_key(token):
    return f"patient-account-recovery-grant:{token}"


def _hash_identity(value):
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:32]


def _allow_request(request, *, scope, identity="", limit=8, window=3600):
    remote = request.META.get("REMOTE_ADDR", "")
    bucket = int(time.time() // window)
    key = f"patient-account-rate:{scope}:{_hash_identity(remote)}:{_hash_identity(identity)}:{bucket}"
    try:
        if cache.add(key, 1, timeout=window + 60):
            return True
        return cache.incr(key) <= limit
    except Exception:
        # Existing form-level and challenge attempt limits remain active even if
        # a development cache backend cannot increment atomically.
        return True


def _mask_phone(value):
    value = str(value or "")
    if len(value) <= 4:
        return "••••"
    return "•" * max(4, len(value) - 4) + value[-4:]


def _read_challenge(token, purpose):
    if not token:
        return None
    data = cache.get(_challenge_key(token))
    if not isinstance(data, dict) or data.get("purpose") != purpose:
        return None
    return data


def _write_challenge(token, data):
    cache.set(_challenge_key(token), data, timeout=OTP_TTL_SECONDS)


def _delete_challenge(token):
    if token:
        cache.delete(_challenge_key(token))


def _send_new_code(*, token, data):
    now = int(time.time())
    if data.get("last_sent_at") and now - int(data["last_sent_at"]) < OTP_RESEND_COOLDOWN_SECONDS:
        raise ValidationError("cooldown")
    code = generate_otp_code()
    data = dict(data)
    data["otp_digest"] = make_password(code)
    data["attempt_count"] = 0
    data["last_sent_at"] = now
    _write_challenge(token, data)
    try:
        send_patient_account_otp(data["phone_e164"], code, data["language"])
    except WhatsAppOtpServiceUnavailable:
        _delete_challenge(token)
        raise
    return data


def _verify_code(*, token, purpose, code):
    data = _read_challenge(token, purpose)
    if data is None:
        return None, "unavailable"
    if not isinstance(code, str) or not OTP_RE.fullmatch(code.strip()):
        code = ""
    if data.get("attempt_count", 0) >= OTP_MAX_ATTEMPTS:
        _delete_challenge(token)
        return None, "attempts"
    if not code or not check_password(code, data.get("otp_digest", "")):
        data["attempt_count"] = int(data.get("attempt_count", 0)) + 1
        if data["attempt_count"] >= OTP_MAX_ATTEMPTS:
            _delete_challenge(token)
            return None, "attempts"
        _write_challenge(token, data)
        return None, "invalid"
    return data, "ok"


def _registration_context(request, language, *, form=None, otp_stage=False, masked_phone=""):
    from apps.patients import views as patient_views

    language = _language(language)
    next_url = patient_views._safe_next_url(request)
    context = patient_views._portal_context(request, language, form=form, next_url=next_url)
    clinic_name = context["clinic"]["name_ar" if language == "ar" else "name_en"]
    register_url = patient_views._portal_url("patient_portal_register", language)
    alternate_language = "en" if language == "ar" else "ar"
    auth_language_url = patient_views._portal_url("patient_portal_register", alternate_language)
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
    recovery_url = patient_views._portal_url("patient_portal_account_recovery", language)
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


class RecoveryPhoneForm(PatientRegistrationForm.base_fields["phone"].formfield().__class__ if False else object):
    """Namespace placeholder retained only to keep import-time behavior simple."""


# Defining these forms locally avoids altering the stable registration form contract.
from django import forms  # noqa: E402  (kept near the flow-specific forms)


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
        self.fields["phone"].label = "رقم الهاتف" if self.language == "ar" else "Phone number"

    def clean_phone(self):
        raw = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw)
        except ValidationError as exc:
            raise ValidationError(auth_error_message("phone_invalid", self.language)) from exc
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
        self.fields["otp"].label = "رمز التحقق" if self.language == "ar" else "Verification code"

    def clean_otp(self):
        value = (self.cleaned_data.get("otp") or "").strip()
        if not OTP_RE.fullmatch(value):
            raise ValidationError(
                "أدخل رمز التحقق المكوّن من 6 أرقام."
                if self.language == "ar"
                else "Enter the 6-digit verification code."
            )
        return value


def _localized_set_password_form(user, data, language):
    form = SetPasswordForm(user=user, data=data)
    if _language(language) == "ar":
        form.fields["new_password1"].label = "كلمة المرور الجديدة"
        form.fields["new_password2"].label = "تأكيد كلمة المرور الجديدة"
    return form


@sensitive_post_parameters("password1", "password2", "otp")
@never_cache
def portal_register(request, language="ar"):
    from apps.patients import views as patient_views

    if not _otp_required():
        return patient_views._legacy_portal_register(request, language=language)

    language = _language(language)
    next_url = patient_views._safe_next_url(request)
    if request.user.is_authenticated:
        return redirect(next_url or patient_views._portal_url("patient_portal_dashboard", language))

    token = request.session.get(REGISTRATION_SESSION_KEY, "")
    verify_requested = request.GET.get("verify") == "1" or request.POST.get("action") in {"verify", "resend"}

    if verify_requested:
        challenge = _read_challenge(token, "registration")
        if challenge is None:
            request.session.pop(REGISTRATION_SESSION_KEY, None)
            messages.error(
                request,
                "انتهت جلسة التحقق. أعد إدخال بيانات التسجيل."
                if language == "ar"
                else "The verification session expired. Enter your registration details again.",
            )
            return redirect(patient_views._portal_url("patient_portal_register", language))

        if request.method == "POST" and request.POST.get("action") == "resend":
            if not _allow_request(request, scope="registration-resend", identity=challenge["phone_e164"], limit=5):
                messages.error(request, "حاول مرة أخرى لاحقًا." if language == "ar" else "Please try again later.")
            else:
                try:
                    challenge = _send_new_code(token=token, data=challenge)
                except ValidationError:
                    messages.info(
                        request,
                        "انتظر قليلًا قبل طلب رمز جديد."
                        if language == "ar"
                        else "Wait briefly before requesting a new code.",
                    )
                except WhatsAppOtpServiceUnavailable:
                    messages.error(
                        request,
                        "خدمة إرسال رمز التحقق غير متاحة حاليًا."
                        if language == "ar"
                        else "The verification-code service is currently unavailable.",
                    )
                else:
                    messages.success(
                        request,
                        "تم إرسال رمز تحقق جديد."
                        if language == "ar"
                        else "A new verification code was sent.",
                    )
            return redirect(f"{patient_views._portal_url('patient_portal_register', language)}?verify=1")

        form = OtpVerifyForm(request.POST if request.method == "POST" else None, language=language)
        if request.method == "POST" and form.is_valid():
            data, reason = _verify_code(
                token=token,
                purpose="registration",
                code=form.cleaned_data["otp"],
            )
            if data is None:
                form.add_error(
                    "otp",
                    "رمز التحقق غير صالح أو منتهي."
                    if language == "ar"
                    else "The verification code is invalid or expired.",
                )
            else:
                user_model = get_user_model()
                try:
                    with transaction.atomic():
                        if user_model.objects.filter(username=data["phone_e164"]).exists():
                            raise IntegrityError("account already exists")
                        user = user_model(
                            username=data["phone_e164"],
                            email=data.get("email", ""),
                            first_name=data.get("full_name", "")[:150],
                            is_staff=False,
                            is_superuser=False,
                            is_active=True,
                        )
                        user.password = data["password_hash"]
                        user.save()
                except IntegrityError:
                    _delete_challenge(token)
                    request.session.pop(REGISTRATION_SESSION_KEY, None)
                    messages.error(
                        request,
                        auth_error_message("registration_generic", language),
                    )
                    return redirect(patient_views._portal_url("patient_portal_register", language))

                _delete_challenge(token)
                request.session.pop(REGISTRATION_SESSION_KEY, None)
                auth_login(request, user)
                messages.success(
                    request,
                    "تم التحقق من رقم الهاتف وإنشاء حساب بوابة المريض."
                    if language == "ar"
                    else "Your phone was verified and the patient portal account was created.",
                )
                return redirect(data.get("next_url") or patient_views._portal_url("patient_portal_dashboard", language))

        return render(
            request,
            "patients/account_otp_verify.html",
            _registration_context(
                request,
                language,
                form=form,
                otp_stage=True,
                masked_phone=_mask_phone(challenge["phone_e164"]),
            ),
        )

    form = PatientRegistrationForm(request.POST if request.method == "POST" else None, language=language)
    if request.method == "POST":
        normalized_phone = rate_limits.normalized_phone_or_empty(request.POST.get("phone"))
        attempt_limit = rate_limits.check_registration_attempt_rate_limit(
            request,
            normalized_phone=normalized_phone,
        )
        form_valid = form.is_valid()
        if not attempt_limit.allowed:
            form.add_error(None, auth_error_message("rate_limit", language))
        elif form_valid:
            token = secrets.token_urlsafe(24)
            data = {
                "purpose": "registration",
                "language": language,
                "phone_e164": form.normalized_phone,
                "full_name": form.cleaned_data["full_name"],
                "email": form.cleaned_data.get("email") or "",
                "password_hash": make_password(form.cleaned_data["password1"]),
                "next_url": next_url,
                "attempt_count": 0,
                "last_sent_at": 0,
            }
            try:
                _send_new_code(token=token, data=data)
            except WhatsAppOtpServiceUnavailable:
                form.add_error(
                    None,
                    "خدمة التحقق عبر واتساب غير متاحة حاليًا. حاول لاحقًا."
                    if language == "ar"
                    else "WhatsApp verification is currently unavailable. Please try again later.",
                )
            else:
                request.session[REGISTRATION_SESSION_KEY] = token
                return redirect(f"{patient_views._portal_url('patient_portal_register', language)}?verify=1")

    return render(
        request,
        "patients/portal_register.html",
        _registration_context(request, language, form=form),
    )


@sensitive_post_parameters("otp", "new_password1", "new_password2")
@never_cache
def portal_account_recovery(request, language="ar"):
    from apps.patients import views as patient_views

    if not _otp_required():
        return patient_views._legacy_portal_account_recovery(request, language=language)

    language = _language(language)
    recovery_url = patient_views._portal_url("patient_portal_account_recovery", language)
    action = request.POST.get("action", "") if request.method == "POST" else ""
    token = request.session.get(RECOVERY_SESSION_KEY, "")

    if request.GET.get("reset") == "1" or action == "reset":
        grant_token = request.session.get(RECOVERY_GRANT_SESSION_KEY, "")
        grant = cache.get(_grant_key(grant_token)) if grant_token else None
        user = None
        if isinstance(grant, dict):
            user = get_user_model().objects.filter(pk=grant.get("user_id"), is_active=True, is_staff=False).first()
        if user is None:
            request.session.pop(RECOVERY_GRANT_SESSION_KEY, None)
            messages.error(
                request,
                "انتهت جلسة استعادة الحساب. ابدأ من جديد."
                if language == "ar"
                else "The recovery session expired. Start again.",
            )
            return redirect(recovery_url)
        form = _localized_set_password_form(
            user,
            request.POST if request.method == "POST" else None,
            language,
        )
        if request.method == "POST" and form.is_valid():
            form.save()
            cache.delete(_grant_key(grant_token))
            request.session.pop(RECOVERY_GRANT_SESSION_KEY, None)
            messages.success(
                request,
                "تم تغيير كلمة المرور. يمكنك تسجيل الدخول الآن."
                if language == "ar"
                else "Your password was changed. You can sign in now.",
            )
            return redirect(patient_views._login_url(language))
        return render(
            request,
            "patients/account_recovery.html",
            _recovery_context(request, language, stage="reset", form=form),
        )

    if request.GET.get("verify") == "1" or action in {"verify", "resend"}:
        challenge = _read_challenge(token, "recovery")
        if challenge is None:
            request.session.pop(RECOVERY_SESSION_KEY, None)
            messages.error(
                request,
                "انتهت جلسة التحقق. ابدأ استعادة الحساب من جديد."
                if language == "ar"
                else "The verification session expired. Start account recovery again.",
            )
            return redirect(recovery_url)

        if request.method == "POST" and action == "resend":
            if challenge.get("user_id"):
                try:
                    _send_new_code(token=token, data=challenge)
                except ValidationError:
                    messages.info(
                        request,
                        "انتظر قليلًا قبل طلب رمز جديد."
                        if language == "ar"
                        else "Wait briefly before requesting a new code.",
                    )
                except WhatsAppOtpServiceUnavailable:
                    messages.error(
                        request,
                        "خدمة إرسال رمز التحقق غير متاحة حاليًا."
                        if language == "ar"
                        else "The verification-code service is currently unavailable.",
                    )
                else:
                    messages.success(request, "تم إرسال رمز جديد." if language == "ar" else "A new code was sent.")
            else:
                messages.info(
                    request,
                    "إذا كان الرقم مرتبطًا بحساب فسيصلك رمز تحقق."
                    if language == "ar"
                    else "If the phone is linked to an account, a verification code will be sent.",
                )
            return redirect(f"{recovery_url}?verify=1")

        form = OtpVerifyForm(request.POST if request.method == "POST" else None, language=language)
        if request.method == "POST" and form.is_valid():
            data, reason = _verify_code(token=token, purpose="recovery", code=form.cleaned_data["otp"])
            if data is None or not data.get("user_id"):
                form.add_error(
                    "otp",
                    "رمز التحقق غير صالح أو منتهي."
                    if language == "ar"
                    else "The verification code is invalid or expired.",
                )
            else:
                grant_token = secrets.token_urlsafe(24)
                cache.set(
                    _grant_key(grant_token),
                    {"user_id": data["user_id"]},
                    timeout=RECOVERY_GRANT_TTL_SECONDS,
                )
                request.session[RECOVERY_GRANT_SESSION_KEY] = grant_token
                _delete_challenge(token)
                request.session.pop(RECOVERY_SESSION_KEY, None)
                return redirect(f"{recovery_url}?reset=1")
        return render(
            request,
            "patients/account_recovery.html",
            _recovery_context(
                request,
                language,
                stage="verify",
                form=form,
                masked_phone=_mask_phone(challenge["phone_e164"]),
            ),
        )

    form = AccountRecoveryStartForm(request.POST if request.method == "POST" else None, language=language)
    if request.method == "POST" and form.is_valid():
        phone = form.normalized_phone
        if not _allow_request(request, scope="recovery-start", identity=phone, limit=6):
            form.add_error(None, auth_error_message("rate_limit", language))
        else:
            user = get_user_model().objects.filter(username=phone, is_active=True, is_staff=False).first()
            token = secrets.token_urlsafe(24)
            data = {
                "purpose": "recovery",
                "language": language,
                "phone_e164": phone,
                "user_id": user.pk if user else None,
                "attempt_count": 0,
                "last_sent_at": 0,
            }
            if user is not None:
                try:
                    _send_new_code(token=token, data=data)
                except WhatsAppOtpServiceUnavailable:
                    form.add_error(
                        None,
                        "خدمة التحقق عبر واتساب غير متاحة حاليًا. حاول لاحقًا."
                        if language == "ar"
                        else "WhatsApp verification is currently unavailable. Please try again later.",
                    )
                    return render(
                        request,
                        "patients/account_recovery.html",
                        _recovery_context(request, language, stage="start", form=form),
                    )
            else:
                # Keep the response shape generic for unknown phone numbers.
                data["otp_digest"] = make_password(generate_otp_code())
                data["last_sent_at"] = int(time.time())
                _write_challenge(token, data)
            request.session[RECOVERY_SESSION_KEY] = token
            messages.info(
                request,
                "إذا كان الرقم مرتبطًا بحساب فسيصلك رمز تحقق عبر واتساب."
                if language == "ar"
                else "If the phone is linked to an account, a verification code will be sent by WhatsApp.",
            )
            return redirect(f"{recovery_url}?verify=1")

    return render(
        request,
        "patients/account_recovery.html",
        _recovery_context(request, language, stage="start", form=form),
    )
