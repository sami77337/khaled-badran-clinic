import uuid

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.booking.phone import normalize_phone
from apps.patients.models import (
    CONSULTATION_MAX_ATTACHMENTS,
    Consultation,
    validate_consultation_upload,
)


GENERIC_LOGIN_ERROR = "We could not sign you in with those details."
GENERIC_REGISTRATION_ERROR = (
    "We could not create an account with these details. Check the information, or "
    "sign in / recover your account if you may already have one."
)
GENERIC_LINK_ERROR = "We could not link an appointment with those details. Check the confirmation link and phone number."


AUTH_ERROR_MESSAGES = {
    "ar": {
        "email_invalid": "أدخل بريدًا إلكترونيًا صالحًا.",
        "full_name_required": "الاسم الكامل مطلوب.",
        "login_generic": "تعذّر تسجيل الدخول بهذه البيانات.",
        "password_confirmation_required": "تأكيد كلمة المرور مطلوب.",
        "password_mismatch": "كلمتا المرور غير متطابقتين.",
        "password_required": "كلمة المرور مطلوبة.",
        "phone_invalid": "أدخل رقم هاتف صالحًا.",
        "phone_required": "رقم الهاتف مطلوب.",
        "rate_limit": "عدد المحاولات كبير. حاول مرة أخرى لاحقًا.",
        "registration_generic": (
            "تعذّر إنشاء الحساب بهذه البيانات. تحقق من البيانات، وإذا كان لديك حساب بالفعل "
            "فجرّب تسجيل الدخول أو استعادة الحساب."
        ),
        "username_required": "اسم المستخدم مطلوب.",
    },
    "en": {
        "email_invalid": "Enter a valid email address.",
        "full_name_required": "Full name is required.",
        "login_generic": GENERIC_LOGIN_ERROR,
        "password_confirmation_required": "Password confirmation is required.",
        "password_mismatch": "Passwords do not match.",
        "password_required": "Password is required.",
        "phone_invalid": "Enter a valid phone number.",
        "phone_required": "Phone number is required.",
        "rate_limit": "Too many attempts. Please try again later.",
        "registration_generic": GENERIC_REGISTRATION_ERROR,
        "username_required": "Username is required.",
    },
}


def auth_error_message(key, language="ar"):
    language = "en" if language == "en" else "ar"
    return AUTH_ERROR_MESSAGES[language][key]


def _localized_password_error(error, language):
    if language != "ar":
        return error

    code = error.code
    if code == "password_too_short":
        min_length = (error.params or {}).get("min_length", 8)
        message = f"كلمة المرور قصيرة جدًا. يجب أن تتكون من {min_length} أحرف على الأقل."
    else:
        message = {
            "password_entirely_numeric": "لا يمكن أن تتكون كلمة المرور من أرقام فقط.",
            "password_too_common": "كلمة المرور شائعة جدًا. اختر كلمة مرور أقوى.",
            "password_too_similar": "كلمة المرور مشابهة جدًا لبياناتك الشخصية.",
        }.get(code)

    if message is None:
        return error
    return ValidationError(message, code=code, params=error.params)


class PatientLoginForm(forms.Form):
    phone = forms.CharField(
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "tel",
                "dir": "ltr",
                "id": "patient-phone",
                "inputmode": "tel",
                "placeholder": "7XXXXXXXX",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "dir": "ltr",
                "id": "patient-password",
            }
        )
    )

    def __init__(self, *args, request=None, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.language = "en" if language == "en" else "ar"
        self.user = None
        self.normalized_phone = ""
        self.fields["phone"].label = "رقم الهاتف" if self.language == "ar" else "Phone number"
        self.fields["password"].label = "كلمة المرور" if self.language == "ar" else "Password"
        self.fields["phone"].error_messages["required"] = auth_error_message(
            "phone_required", self.language
        )
        self.fields["password"].error_messages["required"] = auth_error_message(
            "password_required", self.language
        )

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw_phone)
        except ValidationError as exc:
            raise ValidationError(
                auth_error_message("phone_invalid", self.language),
                code="invalid",
            ) from exc
        return raw_phone.strip()

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        self.user = authenticate(
            self.request,
            username=self.normalized_phone,
            password=cleaned_data.get("password"),
        )
        if self.user is None:
            raise ValidationError(auth_error_message("login_generic", self.language))
        return cleaned_data


class StaffLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "autocapitalize": "none",
                "dir": "ltr",
                "id": "doctor-username",
                "spellcheck": "false",
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "dir": "ltr",
                "id": "doctor-password",
            }
        )
    )

    def __init__(self, *args, request=None, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.language = "en" if language == "en" else "ar"
        self.user = None
        self.fields["username"].label = "اسم المستخدم" if self.language == "ar" else "Username"
        self.fields["password"].label = "كلمة المرور" if self.language == "ar" else "Password"
        self.fields["username"].error_messages["required"] = auth_error_message(
            "username_required", self.language
        )
        self.fields["password"].error_messages["required"] = auth_error_message(
            "password_required", self.language
        )

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        self.user = authenticate(
            self.request,
            username=cleaned_data.get("username"),
            password=cleaned_data.get("password"),
        )
        if self.user is None or not self.user.is_staff:
            self.user = None
            raise ValidationError(auth_error_message("login_generic", self.language))
        return cleaned_data


class PatientRegistrationForm(forms.Form):
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "name",
                "id": "register-full-name",
            }
        ),
    )
    phone = forms.CharField(
        max_length=50,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "tel",
                "dir": "ltr",
                "id": "register-phone",
                "inputmode": "tel",
                "placeholder": "7XXXXXXXX",
            }
        ),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "dir": "ltr",
                "id": "register-email",
            }
        ),
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "dir": "ltr",
                "id": "register-password1",
            }
        )
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "dir": "ltr",
                "id": "register-password2",
            }
        )
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = "en" if language == "en" else "ar"
        self.normalized_phone = ""
        self.fields["full_name"].label = "الاسم الكامل" if self.language == "ar" else "Full name"
        self.fields["phone"].label = "رقم الهاتف" if self.language == "ar" else "Phone number"
        self.fields["email"].label = (
            "البريد الإلكتروني (اختياري)" if self.language == "ar" else "Email (optional)"
        )
        self.fields["password1"].label = "كلمة المرور" if self.language == "ar" else "Password"
        self.fields["password2"].label = "تأكيد كلمة المرور" if self.language == "ar" else "Confirm password"
        self.fields["full_name"].error_messages["required"] = auth_error_message(
            "full_name_required", self.language
        )
        self.fields["phone"].error_messages["required"] = auth_error_message(
            "phone_required", self.language
        )
        self.fields["email"].error_messages["invalid"] = auth_error_message(
            "email_invalid", self.language
        )
        self.fields["password1"].error_messages["required"] = auth_error_message(
            "password_required", self.language
        )
        self.fields["password2"].error_messages["required"] = auth_error_message(
            "password_confirmation_required", self.language
        )

    def clean_full_name(self):
        value = self.cleaned_data["full_name"].strip()
        if not value:
            raise ValidationError(auth_error_message("full_name_required", self.language))
        return value

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw_phone)
        except ValidationError as exc:
            raise ValidationError(
                auth_error_message("phone_invalid", self.language),
                code="invalid",
            ) from exc
        return raw_phone.strip()

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error(
                "password2",
                ValidationError(
                    auth_error_message("password_mismatch", self.language),
                    code="password_mismatch",
                ),
            )

        if self.normalized_phone and get_user_model().objects.filter(username=self.normalized_phone).exists():
            raise ValidationError(auth_error_message("registration_generic", self.language))

        if password1:
            user_model = get_user_model()
            candidate = user_model(
                username=self.normalized_phone or str(uuid.uuid4()),
                email=cleaned_data.get("email") or "",
                first_name=(cleaned_data.get("full_name") or "")[:150],
            )
            try:
                validate_password(password1, user=candidate)
            except ValidationError as exc:
                for error in exc.error_list:
                    self.add_error(
                        "password1",
                        _localized_password_error(error, self.language),
                    )

        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot save an invalid registration form.")

        try:
            with transaction.atomic():
                return get_user_model().objects.create_user(
                    username=self.normalized_phone,
                    email=self.cleaned_data.get("email") or "",
                    password=self.cleaned_data["password1"],
                    first_name=self.cleaned_data["full_name"][:150],
                )
        except IntegrityError:
            if get_user_model().objects.filter(username=self.normalized_phone).exists():
                self.add_error(None, auth_error_message("registration_generic", self.language))
                return None
            raise


class AppointmentLinkForm(forms.Form):
    public_token = forms.CharField(max_length=64)
    phone = forms.CharField(max_length=50)

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = "en" if language == "en" else "ar"
        self.normalized_phone = ""
        self.token = None
        self.fields["public_token"].label = (
            "رمز تأكيد الموعد" if self.language == "ar" else "Appointment confirmation token"
        )
        self.fields["phone"].label = "رقم الهاتف المستخدم في الحجز" if self.language == "ar" else "Booking phone number"
        self.fields["phone"].widget.attrs.update(
            {
                "class": "booking-control",
                "autocomplete": "tel",
                "inputmode": "tel",
                "dir": "ltr",
                "placeholder": "7XXXXXXXX",
            }
        )

    def clean_public_token(self):
        value = (self.cleaned_data.get("public_token") or "").strip()
        try:
            self.token = uuid.UUID(value)
        except (TypeError, ValueError):
            raise ValidationError(GENERIC_LINK_ERROR)
        return value

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw_phone)
        except ValidationError:
            raise ValidationError(GENERIC_LINK_ERROR)
        return raw_phone.strip()


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        if data:
            return [single_clean(data, initial)]
        return []


class ConsultationCreateForm(forms.Form):
    question = forms.CharField(max_length=5000, widget=forms.Textarea(attrs={"rows": 8}))
    attachments = MultipleFileField(required=False)

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = "en" if language == "en" else "ar"
        self.fields["question"].label = "نص الاستشارة" if self.language == "ar" else "Consultation text"
        self.fields["question"].widget.attrs["class"] = "patient-textarea"
        self.fields["attachments"].label = "المرفقات" if self.language == "ar" else "Attachments"
        self.fields["attachments"].widget.attrs["accept"] = ".jpg,.jpeg,.png,.webp,.mp4,.pdf"

    def clean_question(self):
        question = self.cleaned_data["question"].strip()
        if not question:
            raise ValidationError("نص الاستشارة مطلوب." if self.language == "ar" else "Consultation text is required.")
        return question

    def clean_attachments(self):
        attachments = self.cleaned_data.get("attachments") or []
        if len(attachments) > CONSULTATION_MAX_ATTACHMENTS:
            raise ValidationError(
                "يمكن إرفاق 5 ملفات كحد أقصى."
                if self.language == "ar"
                else "You can attach at most 5 files."
            )
        for attachment in attachments:
            try:
                validate_consultation_upload(attachment)
            except ValidationError as exc:
                message = (
                    "أحد المرفقات غير مدعوم أو يتجاوز الحجم المسموح."
                    if self.language == "ar"
                    else "An attachment is unsupported or exceeds the allowed size."
                )
                raise ValidationError(message) from exc
        return attachments


class ConsultationReplyForm(forms.Form):
    staff_reply = forms.CharField(required=False, max_length=5000, widget=forms.Textarea(attrs={"rows": 8}))
    status = forms.ChoiceField(
        choices=(
            (Consultation.Status.ANSWERED, "Answered"),
            (Consultation.Status.CLOSED, "Closed"),
        )
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = "en" if language == "en" else "ar"
        self.fields["staff_reply"].label = "رد الطبيب" if self.language == "ar" else "Doctor reply"
        self.fields["status"].label = "الحالة" if self.language == "ar" else "Status"
        if self.language == "ar":
            self.fields["status"].choices = (
                (Consultation.Status.ANSWERED, "تم الرد"),
                (Consultation.Status.CLOSED, "مغلقة"),
            )

    def clean(self):
        cleaned_data = super().clean()
        reply = (cleaned_data.get("staff_reply") or "").strip()
        if cleaned_data.get("status") == Consultation.Status.ANSWERED and not reply:
            self.add_error(
                "staff_reply",
                "الرد مطلوب عند تحديد تم الرد."
                if self.language == "ar"
                else "A reply is required when marking the consultation answered.",
            )
        cleaned_data["staff_reply"] = reply
        return cleaned_data


class AccountPhoneChangeStartForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    new_phone = forms.CharField(
        max_length=50,
        widget=forms.TextInput(
            attrs={"autocomplete": "tel", "inputmode": "tel", "dir": "ltr", "placeholder": "7XXXXXXXX", "class": "booking-control"}
        ),
    )

    def __init__(self, *args, user, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.language = "en" if language == "en" else "ar"
        self.normalized_phone = ""
        self.fields["current_password"].label = "كلمة المرور الحالية" if self.language == "ar" else "Current password"
        self.fields["new_phone"].label = "رقم الحساب الجديد" if self.language == "ar" else "New account phone"

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise ValidationError("كلمة المرور الحالية غير صحيحة." if self.language == "ar" else "Current password is incorrect.")
        return password

    def clean_new_phone(self):
        raw_phone = self.cleaned_data["new_phone"].strip()
        try:
            self.normalized_phone = normalize_phone(raw_phone)
        except ValidationError as exc:
            raise ValidationError("أدخل رقم هاتف صالحًا." if self.language == "ar" else "Enter a valid phone number.") from exc
        try:
            current_phone = normalize_phone(self.user.username)
        except ValidationError:
            current_phone = self.user.username
        if self.normalized_phone == current_phone:
            raise ValidationError(
                "الرقم الجديد يجب أن يختلف عن رقم الحساب الحالي."
                if self.language == "ar"
                else "The new phone must differ from the current account phone."
            )
        user_model = get_user_model()
        if user_model.objects.filter(username=self.normalized_phone).exclude(pk=self.user.pk).exists():
            raise ValidationError("تعذر استخدام هذا الرقم." if self.language == "ar" else "This phone cannot be used.")
        from apps.patients.models import Patient

        if Patient.objects.filter(phone_e164=self.normalized_phone).exclude(user=self.user).exists():
            raise ValidationError("تعذر استخدام هذا الرقم." if self.language == "ar" else "This phone cannot be used.")
        return raw_phone


class AccountPhoneChangeVerifyForm(forms.Form):
    challenge_id = forms.UUIDField(widget=forms.HiddenInput)
    otp = forms.RegexField(regex=r"^\d{6}$", max_length=6, min_length=6)

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = "en" if language == "en" else "ar"
        self.fields["otp"].label = "رمز التحقق" if self.language == "ar" else "Verification code"
        self.fields["otp"].widget.attrs.update(
            {"autocomplete": "one-time-code", "inputmode": "numeric", "dir": "ltr", "pattern": "[0-9]{6}"}
        )
