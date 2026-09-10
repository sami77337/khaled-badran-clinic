from django import forms
from django.core.exceptions import ValidationError

from apps.booking.phone import normalize_phone
from apps.patients.forms import ConsultationCreateForm


class GuestPhoneForm(forms.Form):
    phone = forms.CharField(max_length=50, widget=forms.TextInput(attrs={
        "type": "tel", "autocomplete": "tel", "dir": "ltr", "inputmode": "tel",
    }))

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self.fields["phone"].label = "رقم واتساب" if language == "ar" else "WhatsApp number"
        self.fields["phone"].help_text = (
            "أدخل رقمك المحلي الأردني أو رقمًا دوليًا يبدأ بـ +."
            if language == "ar" else "Enter a Jordanian mobile number or an international number starting with +."
        )

    def clean_phone(self):
        try:
            return normalize_phone(self.cleaned_data["phone"])
        except ValidationError:
            raise ValidationError("أدخل رقم هاتف صحيحًا." if self.language == "ar" else "Enter a valid phone number.") from None


class GuestOtpForm(forms.Form):
    code = forms.RegexField(regex=r"^[0-9]{6}$", max_length=6, widget=forms.TextInput(attrs={
        "inputmode": "numeric", "autocomplete": "one-time-code", "dir": "ltr", "pattern": "[0-9]{6}",
    }))

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].label = "رمز التحقق" if language == "ar" else "Verification code"
        self.fields["code"].error_messages["invalid"] = (
            "أدخل الرمز المكوّن من 6 أرقام." if language == "ar" else "Enter the 6-digit code."
        )


class GuestConsultationForm(ConsultationCreateForm):
    display_name = forms.CharField(required=False, max_length=100, widget=forms.TextInput(attrs={"autocomplete": "nickname"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_name"].label = "الاسم المعروض (اختياري)" if self.language == "ar" else "Display name (optional)"
        self.order_fields(["display_name", "question", "attachments"])
