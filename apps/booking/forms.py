from django import forms
from django.core.exceptions import ValidationError

from apps.booking.phone import normalize_phone
from apps.booking import services
from apps.booking.selectors import get_active_doctor
from apps.clinic.models import VisitType


class PublicBookingForm(forms.Form):
    full_name = forms.CharField(max_length=255)
    phone = forms.CharField(max_length=50)
    same_as_phone = forms.BooleanField(required=False)
    whatsapp_phone = forms.CharField(max_length=50, required=False)
    visit_type = forms.ModelChoiceField(queryset=VisitType.objects.none(), widget=forms.HiddenInput)
    starts_at = forms.CharField(widget=forms.HiddenInput)
    booking_note = forms.CharField(required=False, widget=forms.Textarea)

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        doctor = get_active_doctor()
        self.fields["visit_type"].queryset = services.public_visit_types()
        self.fields["full_name"].label = "الاسم الكامل" if language == "ar" else "Full name"
        self.fields["phone"].label = "رقم الهاتف" if language == "ar" else "Phone number"
        self.fields["same_as_phone"].label = (
            "استخدام نفس الرقم للواتساب" if language == "ar" else "Use the same number for WhatsApp"
        )
        self.fields["whatsapp_phone"].label = "رقم واتساب" if language == "ar" else "WhatsApp number"
        self.fields["visit_type"].label = "نوع الزيارة" if language == "ar" else "Visit type"
        self.fields["booking_note"].label = "ملاحظة اختيارية" if language == "ar" else "Optional note"
        self.fields["booking_note"].widget.attrs["rows"] = 3
        self.fields["visit_type"].empty_label = None
        self.doctor = doctor
        self.normalized_phone = ""
        self.normalized_whatsapp_phone = ""

    def clean_full_name(self):
        value = self.cleaned_data["full_name"].strip()
        if not value:
            raise ValidationError("Full name is required.")
        return value

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"]
        self.normalized_phone = normalize_phone(raw_phone)
        return raw_phone.strip()

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        same_as_phone = cleaned_data.get("same_as_phone")
        whatsapp_phone = (cleaned_data.get("whatsapp_phone") or "").strip()
        if same_as_phone or not whatsapp_phone:
            self.normalized_whatsapp_phone = self.normalized_phone
            cleaned_data["whatsapp_phone"] = cleaned_data.get("phone", "")
        else:
            self.normalized_whatsapp_phone = normalize_phone(whatsapp_phone)
            cleaned_data["whatsapp_phone"] = whatsapp_phone

        visit_type = cleaned_data.get("visit_type")
        starts_at = cleaned_data.get("starts_at")
        try:
            services.validate_public_booking_request(
                visit_type=visit_type,
                starts_at=starts_at,
                doctor=self.doctor,
            )
        except ValidationError as exc:
            raise ValidationError(exc.messages)

        return cleaned_data

    def save(self):
        if not self.is_valid():
            raise ValueError("Cannot save an invalid booking form.")
        return services.create_public_appointment(
            full_name=self.cleaned_data["full_name"],
            phone_raw=self.cleaned_data["phone"],
            whatsapp_phone_raw=self.cleaned_data.get("whatsapp_phone") or "",
            visit_type_id=self.cleaned_data["visit_type"].id,
            starts_at=self.cleaned_data["starts_at"],
            booking_note=self.cleaned_data.get("booking_note", ""),
        )
