import uuid

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.booking.phone import normalize_phone


GENERIC_LOGIN_ERROR = "We could not sign you in with those details."
GENERIC_REGISTRATION_ERROR = "We could not create an account with those details."
GENERIC_LINK_ERROR = "We could not link an appointment with those details. Check the confirmation link and phone number."


class PatientLoginForm(forms.Form):
    phone = forms.CharField(max_length=50)
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, request=None, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.language = "en" if language == "en" else "ar"
        self.user = None
        self.normalized_phone = ""
        self.fields["phone"].label = "رقم الهاتف" if self.language == "ar" else "Phone number"
        self.fields["password"].label = "كلمة المرور" if self.language == "ar" else "Password"

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw_phone)
        except ValidationError as exc:
            raise ValidationError(exc.messages)
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
            raise ValidationError(GENERIC_LOGIN_ERROR)
        return cleaned_data


class PatientRegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=255)
    phone = forms.CharField(max_length=50)
    email = forms.EmailField(required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = "en" if language == "en" else "ar"
        self.normalized_phone = ""
        self.fields["full_name"].label = "الاسم الكامل" if self.language == "ar" else "Full name"
        self.fields["phone"].label = "رقم الهاتف" if self.language == "ar" else "Phone number"
        self.fields["email"].label = "البريد الإلكتروني اختياري" if self.language == "ar" else "Email, optional"
        self.fields["password1"].label = "كلمة المرور" if self.language == "ar" else "Password"
        self.fields["password2"].label = "تأكيد كلمة المرور" if self.language == "ar" else "Confirm password"

    def clean_full_name(self):
        value = self.cleaned_data["full_name"].strip()
        if not value:
            raise ValidationError("Full name is required.")
        return value

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw_phone)
        except ValidationError as exc:
            raise ValidationError(exc.messages)
        return raw_phone.strip()

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")

        if self.normalized_phone and get_user_model().objects.filter(username=self.normalized_phone).exists():
            raise ValidationError(GENERIC_REGISTRATION_ERROR)

        if password1:
            user_model = get_user_model()
            candidate = user_model(
                username=self.normalized_phone or str(uuid.uuid4()),
                email=cleaned_data.get("email") or "",
                first_name=(cleaned_data.get("full_name") or "")[:150],
            )
            validate_password(password1, user=candidate)

        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot save an invalid registration form.")

        return get_user_model().objects.create_user(
            username=self.normalized_phone,
            email=self.cleaned_data.get("email") or "",
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["full_name"][:150],
        )


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
