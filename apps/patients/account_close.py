"""Patient self-service portal account closure.

Closing a portal identity is deliberately not a medical-record deletion. The
linked Patient record and clinical history remain intact; portal authentication
is disabled and optional public review content is unpublished.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth import logout as auth_logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from apps.core.models import AuditLog, PublicReview
from .localization import use_page_language
from .models import AccountOtpChallenge, AccountPhoneChangeChallenge
from .views import (
    _authenticated_portal_context,
    _login_required,
    _portal_context,
    _portal_url,
)


class CloseAccountForm(forms.Form):
    current_password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "dir": "ltr",
                "id": "close-account-current-password",
            }
        ),
    )
    confirm = forms.BooleanField(required=True)

    def __init__(self, *args, user, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.language = "en" if language == "en" else "ar"
        if self.language == "ar":
            self.fields["current_password"].label = "كلمة المرور الحالية"
            self.fields["confirm"].label = (
                "أفهم أن إغلاق الحساب يوقف تسجيل الدخول، بينما تبقى السجلات الطبية "
                "والمعلومات التي يجب على العيادة الاحتفاظ بها محفوظة بأمان."
            )
            self.fields["current_password"].error_messages["required"] = "كلمة المرور الحالية مطلوبة."
            self.fields["confirm"].error_messages["required"] = "يجب تأكيد فهمك قبل إغلاق الحساب."
        else:
            self.fields["current_password"].label = "Current password"
            self.fields["confirm"].label = (
                "I understand that closing the account disables sign-in while medical records "
                "and information the clinic must retain remain securely stored."
            )
            self.fields["current_password"].error_messages["required"] = "Current password is required."
            self.fields["confirm"].error_messages["required"] = "You must confirm this before closing the account."

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise ValidationError(
                "كلمة المرور الحالية غير صحيحة."
                if self.language == "ar"
                else "The current password is incorrect."
            )
        return password


def _patient_only(request):
    return bool(
        request.user.is_authenticated
        and request.user.is_active
        and not request.user.is_staff
        and not request.user.is_superuser
    )


@sensitive_post_parameters("current_password")
@never_cache
@_login_required
@require_http_methods(["GET", "POST"])
@use_page_language
def close_account(request, language="ar"):
    language = "en" if language == "en" else "ar"
    if not _patient_only(request):
        return HttpResponseForbidden()

    form = CloseAccountForm(
        request.POST if request.method == "POST" else None,
        user=request.user,
        language=language,
    )
    if request.method == "POST" and form.is_valid():
        closed = False
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if user.is_active and not user.is_staff and not user.is_superuser:
                # Re-check against the locked account so a concurrent credential
                # change cannot turn an earlier form validation into authorization.
                if not user.check_password(form.cleaned_data["current_password"]):
                    form.add_error(
                        "current_password",
                        "كلمة المرور الحالية غير صحيحة."
                        if language == "ar"
                        else "The current password is incorrect.",
                    )
                else:
                    PublicReview.objects.filter(
                        submitted_by=user,
                        source=PublicReview.Source.PATIENT_PORTAL,
                    ).update(is_active=False, is_featured=False)
                    AccountPhoneChangeChallenge.objects.filter(user=user).delete()
                    AccountOtpChallenge.objects.filter(user=user).delete()
                    user.is_active = False
                    user.save(update_fields=["is_active"])
                    AuditLog.objects.create(
                        user=user,
                        action=AuditLog.Action.STATUS_CHANGE,
                        app_label="auth",
                        model_name="User",
                        object_id=str(user.pk),
                        object_repr="Patient portal account",
                        message="Patient closed portal account; retained medical records were not deleted.",
                        metadata={
                            "account_closed": True,
                            "medical_records_retained": True,
                            "public_review_unpublished": True,
                        },
                    )
                    closed = True

        if closed:
            auth_logout(request)
            return redirect(_portal_url("patient_portal_account_closed", language))

    return render(
        request,
        "patients/account_close.html",
        _authenticated_portal_context(
            request,
            language,
            form=form,
            portal_section="account",
            page_title="إغلاق الحساب" if language == "ar" else "Close Account",
        ),
    )


@never_cache
@require_http_methods(["GET"])
@use_page_language
def account_closed(request, language="ar"):
    language = "en" if language == "en" else "ar"
    if request.user.is_authenticated and not request.user.is_staff:
        return redirect(_portal_url("patient_portal_account", language))
    return render(
        request,
        "patients/account_closed.html",
        _portal_context(
            request,
            language,
            page_key="account_closed",
            page_title="تم إغلاق الحساب" if language == "ar" else "Account Closed",
            meta_description=(
                "تم إغلاق الوصول إلى حساب المريض مع الحفاظ على السجلات المطلوبة بأمان."
                if language == "ar"
                else "Patient portal access has been closed while required records remain securely retained."
            ),
        ),
    )
