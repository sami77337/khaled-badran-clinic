from django import forms
from django.core.exceptions import ValidationError

from apps.booking import operations
from apps.booking.phone import normalize_phone
from apps.booking import services
from apps.booking.selectors import get_active_doctor
from apps.clinic.models import VisitType


PUBLIC_BOOKING_ERROR_COPY = {
    "ar": {
        "full_name_required": "يرجى إدخال الاسم الكامل.",
        "phone_required": "يرجى إدخال رقم الهاتف.",
        "phone_invalid": "يرجى إدخال رقم هاتف أردني صحيح أو رقم دولي يبدأ بعلامة +.",
        "whatsapp_invalid": "يرجى إدخال رقم واتساب صحيح أو اختيار استخدام رقم الهاتف نفسه.",
        "visit_type_invalid": "نوع الزيارة المحدد غير متاح. يرجى اختيار نوع زيارة آخر.",
        "slot_invalid": "وقت الموعد المحدد غير صالح. يرجى اختيار وقت متاح.",
        "slot_unavailable": "لم يعد وقت الموعد المحدد متاحًا. يرجى اختيار وقت آخر.",
        "booking_unavailable": "الحجز الإلكتروني غير متاح حاليًا.",
        "doctor_unavailable": "لا يوجد طبيب متاح للحجز الإلكتروني حاليًا.",
        "too_many_attempts": "تم تجاوز عدد محاولات الحجز المسموح. يرجى الانتظار قبل المحاولة مرة أخرى.",
        "phone_limit": "بلغ رقم الهاتف الحد اليومي لمحاولات الحجز.",
        "generic": "تعذر التحقق من طلب الحجز. يرجى مراجعة البيانات والمحاولة مرة أخرى.",
    },
    "en": {
        "full_name_required": "Please enter the full name.",
        "phone_required": "Please enter a phone number.",
        "phone_invalid": "Enter a valid Jordanian mobile number or an international number starting with +.",
        "whatsapp_invalid": "Enter a valid WhatsApp number or choose to use the same phone number.",
        "visit_type_invalid": "The selected visit type is unavailable. Choose another visit type.",
        "slot_invalid": "The selected appointment time is invalid. Choose an available time.",
        "slot_unavailable": "The selected appointment time is no longer available. Choose another time.",
        "booking_unavailable": "Online booking is currently unavailable.",
        "doctor_unavailable": "No doctor is currently available for online booking.",
        "too_many_attempts": "Too many booking attempts. Please wait before trying again.",
        "phone_limit": "This phone number has reached the daily booking attempt limit.",
        "generic": "We could not validate the booking request. Review the details and try again.",
    },
}


PUBLIC_BOOKING_ERROR_KEYS = {
    "Full name is required.": "full_name_required",
    "Phone number is required.": "phone_required",
    "Enter a plausible international phone number.": "phone_invalid",
    "Enter a Jordanian mobile number or an international number starting with +.": "phone_invalid",
    "Select an active visit type.": "visit_type_invalid",
    "Select a valid appointment time.": "slot_invalid",
    "This appointment time is no longer available.": "slot_unavailable",
    "Online booking is currently unavailable.": "booking_unavailable",
    "No active doctor is available for public booking.": "doctor_unavailable",
    "Appointment end time must be after start time.": "slot_invalid",
    "Too many booking attempts. Please wait before trying again.": "too_many_attempts",
    "This phone number has reached the daily booking attempt limit.": "phone_limit",
}


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
        self.error_copy = PUBLIC_BOOKING_ERROR_COPY[language]
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
        self.fields["full_name"].error_messages["required"] = self.error_copy["full_name_required"]
        self.fields["phone"].error_messages["required"] = self.error_copy["phone_required"]
        self.fields["visit_type"].error_messages.update(
            {
                "required": self.error_copy["visit_type_invalid"],
                "invalid_choice": self.error_copy["visit_type_invalid"],
            }
        )
        self.fields["starts_at"].error_messages["required"] = self.error_copy["slot_invalid"]
        self.fields["full_name"].widget.attrs.update(
            {
                "class": "booking-control",
                "autocomplete": "name",
                "placeholder": "الاسم الكامل" if language == "ar" else "Full name",
            }
        )
        self.fields["phone"].widget.attrs.update(
            {
                "class": "booking-control",
                "autocomplete": "tel",
                "inputmode": "tel",
                "dir": "ltr",
                "placeholder": "07XXXXXXXX أو +962…" if language == "ar" else "07XXXXXXXX or +962…",
            }
        )
        self.fields["whatsapp_phone"].widget.attrs.update(
            {
                "class": "booking-control",
                "autocomplete": "tel",
                "inputmode": "tel",
                "dir": "ltr",
                "placeholder": "اختياري" if language == "ar" else "Optional",
            }
        )
        self.fields["booking_note"].widget.attrs.update(
            {
                "class": "booking-control booking-textarea",
                "rows": 3,
                "placeholder": "سبب الزيارة أو ملاحظة مختصرة" if language == "ar" else "Reason for visit or a brief note",
            }
        )
        self.fields["same_as_phone"].widget.attrs["class"] = "booking-checkbox"
        self.fields["visit_type"].empty_label = None
        self.doctor = doctor
        self.normalized_phone = ""
        self.normalized_whatsapp_phone = ""

    def localized_error(self, error, *, fallback_key="generic"):
        messages = getattr(error, "messages", None) or [str(error)]
        localized_messages = []
        for message in messages:
            key = PUBLIC_BOOKING_ERROR_KEYS.get(message, fallback_key)
            localized_messages.append(self.error_copy[key])
        return ValidationError(localized_messages)

    def clean_full_name(self):
        value = self.cleaned_data["full_name"].strip()
        if not value:
            raise ValidationError(self.error_copy["full_name_required"])
        return value

    def clean_phone(self):
        raw_phone = self.cleaned_data["phone"]
        try:
            self.normalized_phone = normalize_phone(raw_phone)
        except ValidationError as exc:
            raise self.localized_error(exc, fallback_key="phone_invalid") from exc
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
            try:
                self.normalized_whatsapp_phone = normalize_phone(whatsapp_phone)
            except ValidationError as exc:
                self.add_error(
                    "whatsapp_phone",
                    self.localized_error(exc, fallback_key="whatsapp_invalid"),
                )
                return cleaned_data
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
            raise self.localized_error(exc)

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


class StatusNoteForm(forms.Form):
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Staff note",
    )

    def clean_note(self):
        return (self.cleaned_data.get("note") or "").strip()


class CancelAppointmentForm(StatusNoteForm):
    note = forms.CharField(
        required=True,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Cancellation reason",
    )

    def clean_note(self):
        note = super().clean_note()
        if not note:
            raise ValidationError("Cancellation reason is required.")
        return note


class MarkNoShowForm(StatusNoteForm):
    note = forms.CharField(
        required=True,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="No-show reason",
    )

    def clean_note(self):
        note = super().clean_note()
        if not note:
            raise ValidationError("No-show reason is required.")
        return note


class RescheduleAppointmentForm(forms.Form):
    starts_at = forms.DateTimeField(
        input_formats=[
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label="New appointment time",
    )
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Reschedule note",
    )

    def __init__(self, *args, appointment, **kwargs):
        super().__init__(*args, **kwargs)
        self.appointment = appointment

    def clean_starts_at(self):
        starts_at = self.cleaned_data["starts_at"]
        try:
            starts_at, _ = operations.validate_reschedule_target(self.appointment, starts_at)
        except ValidationError as exc:
            raise ValidationError(exc.messages)
        return starts_at

    def clean_note(self):
        return (self.cleaned_data.get("note") or "").strip()
