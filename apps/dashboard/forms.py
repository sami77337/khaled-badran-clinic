import unicodedata

from django import forms
from django.core.exceptions import ValidationError

from apps.booking.models import Appointment
from apps.clinic.models import ClosedDay, DoctorSchedule, DoctorScheduleOverride, VisitType
from apps.records.models import (
    ClinicalNote,
    PublicCase,
    RecordMedia,
    RecordMediaFolder,
    VisitRecord,
)
from apps.records.public_cases import (
    PUBLIC_CASE_ROLE_AFTER,
    PUBLIC_CASE_ROLE_BEFORE,
    PUBLIC_CASE_ROLE_VIDEO,
    PUBLIC_CASE_ROLE_VIDEO_COVER,
)


DATETIME_INPUT_FORMATS = [
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
]

TIME_INPUT_FORMATS = ["%H:%M"]
MAX_VISIT_DURATION_MINUTES = 65_535
MAX_BOOKING_HORIZON_DAYS = 3_650
MAX_BOOKING_RULE_MINUTES = 5_256_000
PUBLIC_CASE_NOTE_MAX_LENGTH = 500
PUBLIC_CASE_TITLE_MAX_LENGTH = 180

RECORD_FIELD_ERROR_MESSAGES = {
    "ar": {
        "required": "هذا الحقل مطلوب.",
        "invalid": "أدخل قيمة صحيحة.",
        "invalid_choice": "حدد خيارا صحيحا.",
        "max_length": "تأكد من أن القيمة لا تتجاوز الحد الأقصى المسموح.",
        "empty": "الملف المرفوع فارغ.",
        "missing": "لم يتم إرسال أي ملف.",
        "contradiction": "تعذر معالجة اختيار الملف.",
    },
    "en": {
        "required": "This field is required.",
        "invalid": "Enter a valid value.",
        "invalid_choice": "Select a valid choice.",
        "max_length": "Ensure this value does not exceed the allowed maximum.",
        "empty": "The uploaded file is empty.",
        "missing": "No file was submitted.",
        "contradiction": "The file selection could not be processed.",
    },
}

RECORD_MODEL_ERROR_TRANSLATIONS_AR = {
    "Appointment must belong to the selected patient.": "يجب أن يكون الموعد مرتبطا بالمريض المحدد.",
    "Visit must belong to the selected patient.": "يجب أن تكون الزيارة مرتبطة بالمريض المحدد.",
    "Folder must belong to the selected patient.": "يجب أن يكون المجلد مرتبطا بالمريض المحدد.",
    "Reference visit must belong to the selected patient.": (
        "يجب أن تكون الزيارة المرجعية مرتبطة بالمريض المحدد."
    ),
    "Public case must belong to the selected patient.": (
        "يجب أن تكون الحالة العامة مرتبطة بالمريض المحدد."
    ),
    "Folder name is required.": "اسم المجلد مطلوب.",
    "A folder with this name already exists for this patient.": (
        "يوجد مجلد بهذا الاسم لهذا المريض."
    ),
    "Private media file is required.": "ملف الوسائط الخاصة مطلوب.",
    "Unsupported image file extension.": "امتداد ملف الصورة غير مدعوم.",
    "Unsupported image content type.": "نوع محتوى الصورة غير مدعوم.",
    "Image file exceeds the allowed size.": "يتجاوز ملف الصورة الحجم المسموح.",
    "Unsupported short video file extension.": "امتداد ملف الفيديو القصير غير مدعوم.",
    "Unsupported short video content type.": "نوع محتوى الفيديو القصير غير مدعوم.",
    "Short Video file exceeds the allowed size.": "يتجاوز ملف الفيديو القصير الحجم المسموح.",
    "Public case media requires confirmed consent.": "تتطلب وسائط الحالة العامة موافقة مؤكدة.",
}

NOTE_TYPE_CHOICES = {
    "ar": (
        (ClinicalNote.NoteType.DOCTOR_NOTE, "ملاحظة طبيب"),
        (ClinicalNote.NoteType.STAFF_NOTE, "ملاحظة طاقم"),
        (ClinicalNote.NoteType.FOLLOW_UP, "متابعة"),
    ),
    "en": ClinicalNote.NoteType.choices,
}

MEDIA_TYPE_CHOICES = {
    "ar": (
        (RecordMedia.MediaType.IMAGE, "صورة"),
        (RecordMedia.MediaType.SHORT_VIDEO, "فيديو قصير"),
    ),
    "en": RecordMedia.MediaType.choices,
}

PRIVATE_MEDIA_VISIBILITY_CHOICES = {
    "ar": (
        (RecordMedia.Visibility.PRIVATE_ONLY, "خاص فقط"),
        (RecordMedia.Visibility.VISIBLE_TO_PATIENT, "ظاهر للمريض"),
    ),
    "en": (
        (RecordMedia.Visibility.PRIVATE_ONLY, "Private only"),
        (RecordMedia.Visibility.VISIBLE_TO_PATIENT, "Visible to patient"),
    ),
}


def _scheduling_copy(language, arabic, english):
    return english if language == "en" else arabic


def _normalized_public_text(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return " ".join(normalized.split())


def _normalized_digits(value):
    digits = []
    for character in unicodedata.normalize("NFKC", str(value or "")):
        if not character.isdigit():
            continue
        try:
            digits.append(str(unicodedata.digit(character)))
        except (TypeError, ValueError):
            digits.append(character)
    return "".join(digits)


def _contains_current_patient_pii(value, patient):
    normalized_value = _normalized_public_text(value)
    normalized_name = _normalized_public_text(patient.full_name)
    generic_names = {"patient", "مريض"}
    if (
        normalized_name
        and normalized_name not in generic_names
        and normalized_name in normalized_value
    ):
        return True

    content_digits = _normalized_digits(value)
    for phone_value in (
        patient.phone_raw,
        patient.phone_e164,
        patient.whatsapp_phone_raw,
        patient.whatsapp_phone_e164,
    ):
        phone_digits = _normalized_digits(phone_value)
        if phone_digits and len(phone_digits) >= 7 and phone_digits in content_digits:
            return True
    return False


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        uploaded_files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(item, initial) for item in uploaded_files]


class _LocalizedRecordFormMixin:
    language = "ar"

    def _configure_record_localization(
        self,
        *,
        language,
        labels,
        help_texts=None,
        choices=None,
    ):
        self.language = "en" if language == "en" else "ar"
        localized_labels = labels[self.language]
        localized_help_texts = (help_texts or {}).get(self.language, {})
        localized_choices = (choices or {}).get(self.language, {})
        field_errors = RECORD_FIELD_ERROR_MESSAGES[self.language]

        for field_name, field in self.fields.items():
            if field_name in localized_labels:
                field.label = localized_labels[field_name]
            if field_name in localized_help_texts:
                field.help_text = localized_help_texts[field_name]
            if field_name in localized_choices:
                field.choices = localized_choices[field_name]
            for error_code, message in field_errors.items():
                if error_code in field.error_messages:
                    field.error_messages[error_code] = message

    def full_clean(self):
        super().full_clean()
        if self.language != "ar" or not self._errors:
            return
        for error_list in self._errors.values():
            for error in error_list.data:
                if not isinstance(error, ValidationError):
                    continue
                translated_message = RECORD_MODEL_ERROR_TRANSLATIONS_AR.get(error.message)
                if translated_message:
                    error.message = translated_message


class _WeeklyPeriodTimesForm(forms.Form):
    start_time = forms.TimeField(
        input_formats=TIME_INPUT_FORMATS,
        widget=forms.TimeInput(attrs={"type": "time", "step": "60"}, format="%H:%M"),
    )
    end_time = forms.TimeField(
        input_formats=TIME_INPUT_FORMATS,
        widget=forms.TimeInput(attrs={"type": "time", "step": "60"}, format="%H:%M"),
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self.fields["start_time"].label = _scheduling_copy(language, "وقت البدء", "Start time")
        self.fields["end_time"].label = _scheduling_copy(language, "وقت الانتهاء", "End time")
        invalid_time = _scheduling_copy(
            language,
            "أدخل وقتاً صالحاً بصيغة ساعة ودقيقة.",
            "Enter a valid time in hours and minutes.",
        )
        for field in self.fields.values():
            field.error_messages["required"] = invalid_time
            field.error_messages["invalid"] = invalid_time

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and start_time >= end_time:
            self.add_error(
                "end_time",
                _scheduling_copy(
                    self.language,
                    "يجب أن يكون وقت الانتهاء بعد وقت البدء.",
                    "End time must be after start time.",
                ),
            )
        return cleaned_data

    def validate_no_overlap(self, *, doctor, weekday, exclude_period_id=None):
        if self.errors:
            return False
        start_time = self.cleaned_data["start_time"]
        end_time = self.cleaned_data["end_time"]
        overlaps = DoctorSchedule.objects.filter(
            doctor=doctor,
            weekday=weekday,
            is_active=True,
            start_time__lt=end_time,
            end_time__gt=start_time,
        )
        if exclude_period_id is not None:
            overlaps = overlaps.exclude(pk=exclude_period_id)
        if overlaps.exists():
            self.add_error(
                "start_time",
                _scheduling_copy(
                    self.language,
                    "تتداخل هذه الفترة مع فترة عمل نشطة في اليوم نفسه.",
                    "This period overlaps an active working period on the same weekday.",
                ),
            )
            return False
        return True


class WeeklyPeriodCreateForm(_WeeklyPeriodTimesForm):
    weekday = forms.TypedChoiceField(
        choices=DoctorSchedule.Weekday.choices,
        coerce=int,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, language=language, **kwargs)
        self.fields["weekday"].error_messages["required"] = _scheduling_copy(
            language,
            "اختر يوم عمل صالحاً.",
            "Select a valid weekday.",
        )
        self.fields["weekday"].error_messages["invalid_choice"] = _scheduling_copy(
            language,
            "اختر يوم عمل صالحاً.",
            "Select a valid weekday.",
        )


class WeeklyPeriodUpdateForm(_WeeklyPeriodTimesForm):
    pass


class ClosureCreateForm(forms.ModelForm):
    class Meta:
        model = ClosedDay
        fields = ["date", "reason_ar", "reason_en"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        labels = {
            "date": ("التاريخ", "Date"),
            "reason_ar": ("السبب بالعربية (اختياري)", "Arabic reason (optional)"),
            "reason_en": ("السبب بالإنجليزية (اختياري)", "English reason (optional)"),
        }
        for name, (arabic, english) in labels.items():
            self.fields[name].label = _scheduling_copy(language, arabic, english)
        invalid_date = _scheduling_copy(language, "أدخل تاريخاً صالحاً.", "Enter a valid date.")
        self.fields["date"].error_messages.update(
            {"required": invalid_date, "invalid": invalid_date}
        )


class SpecialHoursForm(forms.ModelForm):
    class Meta:
        model = DoctorScheduleOverride
        fields = ["date", "start_time", "end_time", "reason_ar", "reason_en"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "start_time": forms.TimeInput(
                attrs={"type": "time", "step": "60"},
                format="%H:%M",
            ),
            "end_time": forms.TimeInput(
                attrs={"type": "time", "step": "60"},
                format="%H:%M",
            ),
        }

    def __init__(self, *args, language="ar", doctor=None, locked_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self.doctor = doctor
        self.locked_date = locked_date
        if doctor is not None:
            self.instance.doctor = doctor
        if locked_date is not None:
            self.fields["date"].widget = forms.HiddenInput()
            self.initial["date"] = locked_date

        labels = {
            "date": ("التاريخ", "Date"),
            "start_time": ("وقت البدء", "Start time"),
            "end_time": ("وقت الانتهاء", "End time"),
            "reason_ar": ("السبب بالعربية (اختياري)", "Arabic reason (optional)"),
            "reason_en": ("السبب بالإنجليزية (اختياري)", "English reason (optional)"),
        }
        for name, (arabic, english) in labels.items():
            self.fields[name].label = _scheduling_copy(language, arabic, english)

        invalid_date = _scheduling_copy(language, "أدخل تاريخاً صالحاً.", "Enter a valid date.")
        invalid_time = _scheduling_copy(
            language,
            "أدخل وقتاً صالحاً بصيغة ساعة ودقيقة.",
            "Enter a valid time in hours and minutes.",
        )
        self.fields["date"].error_messages.update(
            {"required": invalid_date, "invalid": invalid_date}
        )
        for name in ("start_time", "end_time"):
            self.fields[name].input_formats = TIME_INPUT_FORMATS
            self.fields[name].error_messages.update(
                {"required": invalid_time, "invalid": invalid_time}
            )

    def clean_date(self):
        value = self.cleaned_data["date"]
        if self.locked_date is not None and value != self.locked_date:
            raise forms.ValidationError(
                _scheduling_copy(
                    self.language,
                    "يجب أن يبقى التعديل في التاريخ المحدد.",
                    "The update must remain on the selected date.",
                )
            )
        return value

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and start_time >= end_time:
            self.add_error(
                "end_time",
                _scheduling_copy(
                    self.language,
                    "يجب أن يكون وقت الانتهاء بعد وقت البدء.",
                    "End time must be after start time.",
                ),
            )
        return cleaned_data

    def validate_no_overlap(self, *, doctor, exclude_period_id=None):
        if self.errors:
            return False
        overlaps = DoctorScheduleOverride.objects.filter(
            doctor=doctor,
            date=self.cleaned_data["date"],
            is_active=True,
            start_time__lt=self.cleaned_data["end_time"],
            end_time__gt=self.cleaned_data["start_time"],
        )
        if exclude_period_id is not None:
            overlaps = overlaps.exclude(pk=exclude_period_id)
        if overlaps.exists():
            self.add_error(
                "start_time",
                _scheduling_copy(
                    self.language,
                    "تتداخل هذه الفترة مع ساعات خاصة نشطة في التاريخ نفسه.",
                    "This period overlaps active Special Hours on the same date.",
                ),
            )
            return False
        return True


class SpecialHoursDateForm(forms.Form):
    date = forms.DateField(
        widget=forms.HiddenInput(),
        input_formats=["%Y-%m-%d"],
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date"].label = _scheduling_copy(language, "التاريخ", "Date")
        invalid_date = _scheduling_copy(language, "أدخل تاريخاً صالحاً.", "Enter a valid date.")
        self.fields["date"].error_messages.update(
            {"required": invalid_date, "invalid": invalid_date}
        )


class VisitTypeDurationForm(forms.Form):
    duration_minutes = forms.IntegerField(
        min_value=1,
        max_value=MAX_VISIT_DURATION_MINUTES,
        widget=forms.NumberInput(attrs={"min": "1", "max": str(MAX_VISIT_DURATION_MINUTES)}),
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["duration_minutes"].label = _scheduling_copy(
            language,
            "مدة الخدمة بالدقائق",
            "Service duration in minutes",
        )
        self.fields["duration_minutes"].error_messages.update(
            {
                "required": _scheduling_copy(
                    language, "أدخل مدة الخدمة بالدقائق.", "Enter the service duration in minutes."
                ),
                "invalid": _scheduling_copy(
                    language, "أدخل عدداً صحيحاً صالحاً.", "Enter a valid whole number."
                ),
                "min_value": _scheduling_copy(
                    language, "يجب أن تكون المدة دقيقة واحدة على الأقل.", "Duration must be at least 1 minute."
                ),
                "max_value": _scheduling_copy(
                    language,
                    "تتجاوز المدة الحد الذي يدعمه حقل الخدمة.",
                    "Duration exceeds the service field's supported limit.",
                ),
            }
        )


class VisitTypeCreateForm(forms.ModelForm):
    duration_minutes = forms.IntegerField(
        min_value=1,
        max_value=MAX_VISIT_DURATION_MINUTES,
        widget=forms.NumberInput(attrs={"min": "1", "max": str(MAX_VISIT_DURATION_MINUTES)}),
    )

    class Meta:
        model = VisitType
        fields = ["name_ar", "name_en", "duration_minutes"]

    def __init__(self, *args, language="ar", doctor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor = doctor
        if doctor is not None:
            self.instance.doctor = doctor
        labels = {
            "name_ar": ("اسم الخدمة بالعربية", "Arabic service name"),
            "name_en": ("اسم الخدمة بالإنجليزية", "English service name"),
            "duration_minutes": ("مدة الخدمة بالدقائق", "Service duration in minutes"),
        }
        for name, (arabic, english) in labels.items():
            self.fields[name].label = _scheduling_copy(language, arabic, english)
            self.fields[name].error_messages["required"] = _scheduling_copy(
                language,
                "هذا الحقل مطلوب.",
                "This field is required.",
            )
        duration = self.fields["duration_minutes"]
        duration.error_messages.update(
            {
                "invalid": _scheduling_copy(
                    language, "أدخل عدداً صحيحاً صالحاً.", "Enter a valid whole number."
                ),
                "min_value": _scheduling_copy(
                    language,
                    "يجب أن تكون المدة دقيقة واحدة على الأقل.",
                    "Duration must be at least 1 minute.",
                ),
                "max_value": _scheduling_copy(
                    language,
                    "تتجاوز المدة الحد الذي يدعمه حقل الخدمة.",
                    "Duration exceeds the service field's supported limit.",
                ),
            }
        )

    def save(self, commit=True):
        visit_type = super().save(commit=False)
        visit_type.doctor = self.doctor
        visit_type.is_active = True
        if commit:
            visit_type.save()
        return visit_type


class BookingRulesForm(forms.Form):
    booking_enabled = forms.TypedChoiceField(
        choices=(("true", "Enabled"), ("false", "Disabled")),
        coerce=lambda value: value == "true",
        widget=forms.Select,
    )
    booking_min_lead_minutes = forms.IntegerField(
        min_value=0,
        max_value=MAX_BOOKING_RULE_MINUTES,
        widget=forms.NumberInput(attrs={"min": "0", "max": str(MAX_BOOKING_RULE_MINUTES)}),
    )
    booking_max_days_ahead = forms.IntegerField(
        min_value=1,
        max_value=MAX_BOOKING_HORIZON_DAYS,
        widget=forms.NumberInput(attrs={"min": "1", "max": str(MAX_BOOKING_HORIZON_DAYS)}),
    )
    booking_slot_interval_minutes = forms.IntegerField(
        min_value=1,
        max_value=MAX_BOOKING_RULE_MINUTES,
        widget=forms.NumberInput(attrs={"min": "1", "max": str(MAX_BOOKING_RULE_MINUTES)}),
    )
    appointment_reminder_offset_minutes = forms.IntegerField(
        min_value=0,
        max_value=MAX_BOOKING_RULE_MINUTES,
        widget=forms.NumberInput(attrs={"min": "0", "max": str(MAX_BOOKING_RULE_MINUTES)}),
    )

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "booking_enabled": ("الحجز الإلكتروني مفعل", "Online booking enabled"),
            "booking_min_lead_minutes": ("الحد الأدنى قبل الموعد", "Minimum booking lead time"),
            "booking_max_days_ahead": ("السماح بالحجز حتى", "Allow booking up to"),
            "booking_slot_interval_minutes": (
                "تبدأ أوقات الحجز كل",
                "Appointment slots start every",
            ),
            "appointment_reminder_offset_minutes": (
                "وقت التذكير قبل الموعد",
                "Appointment reminder lead time",
            ),
        }
        units = {
            "booking_enabled": ("مفعل أو غير مفعل", "Enabled or disabled"),
            "booking_min_lead_minutes": ("بالدقائق", "Minutes"),
            "booking_max_days_ahead": ("يوماً مقدماً", "Days in advance"),
            "booking_slot_interval_minutes": ("دقيقة", "Minutes"),
            "appointment_reminder_offset_minutes": ("بالدقائق", "Minutes"),
        }
        for name, (arabic, english) in labels.items():
            field = self.fields[name]
            field.label = _scheduling_copy(language, arabic, english)
            field.help_text = _scheduling_copy(language, *units[name])
            field.error_messages["required"] = _scheduling_copy(
                language,
                "هذه القيمة مطلوبة.",
                "This value is required.",
            )
            if isinstance(field, forms.IntegerField):
                field.error_messages["invalid"] = _scheduling_copy(
                    language,
                    "أدخل عدداً صحيحاً صالحاً.",
                    "Enter a valid whole number.",
                )
                field.error_messages["min_value"] = _scheduling_copy(
                    language,
                    "القيمة أقل من الحد الأدنى المسموح.",
                    "The value is below the allowed minimum.",
                )
                field.error_messages["max_value"] = _scheduling_copy(
                    language,
                    "القيمة تتجاوز الحد الوقائي المدعوم.",
                    "The value exceeds the supported defensive limit.",
                )
        self.fields["booking_enabled"].choices = (
            ("true", _scheduling_copy(language, "مفعل", "Enabled")),
            ("false", _scheduling_copy(language, "غير مفعل", "Disabled")),
        )


class StaffVisitRecordForm(_LocalizedRecordFormMixin, forms.ModelForm):
    visit_date = forms.DateTimeField(
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        label="تاريخ الزيارة",
    )

    class Meta:
        model = VisitRecord
        fields = [
            "appointment",
            "visit_date",
            "visit_reason",
            "doctor_notes",
            "diagnosis_plan",
            "instructions",
            "follow_up_notes",
            "is_visible_to_patient",
        ]
        labels = {
            "appointment": "الموعد المرتبط",
            "visit_reason": "سبب الزيارة",
            "doctor_notes": "ملاحظات الطبيب",
            "diagnosis_plan": "الخطة المكتوبة يدويا",
            "instructions": "تعليمات للمريض",
            "follow_up_notes": "ملاحظات المتابعة",
            "is_visible_to_patient": "ظاهر للمريض",
        }
        widgets = {
            "visit_reason": forms.Textarea(attrs={"rows": 3}),
            "doctor_notes": forms.Textarea(attrs={"rows": 4}),
            "diagnosis_plan": forms.Textarea(attrs={"rows": 4}),
            "instructions": forms.Textarea(attrs={"rows": 3}),
            "follow_up_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, patient, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.instance.patient = patient
        self.fields["appointment"].required = False
        self.fields["appointment"].empty_label = _scheduling_copy(
            language,
            "بدون موعد مرتبط",
            "No linked appointment",
        )
        self.fields["appointment"].queryset = (
            Appointment.objects.filter(patient=patient)
            .select_related("doctor", "visit_type")
            .order_by("-starts_at", "-id")
        )
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "appointment": "الموعد المرتبط",
                    "visit_date": "تاريخ الزيارة",
                    "visit_reason": "سبب الزيارة",
                    "doctor_notes": "ملاحظات الطبيب",
                    "diagnosis_plan": "التشخيص / الخطة",
                    "instructions": "تعليمات للمريض",
                    "follow_up_notes": "ملاحظات المتابعة",
                    "is_visible_to_patient": "ظاهر للمريض",
                },
                "en": {
                    "appointment": "Linked appointment",
                    "visit_date": "Visit date",
                    "visit_reason": "Visit reason",
                    "doctor_notes": "Doctor notes",
                    "diagnosis_plan": "Diagnosis / plan",
                    "instructions": "Patient instructions",
                    "follow_up_notes": "Follow-up notes",
                    "is_visible_to_patient": "Visible to patient",
                },
            },
            help_texts={
                "ar": {
                    "doctor_notes": "محتوى يدوي يكتبه الطبيب أو الطاقم.",
                    "diagnosis_plan": "تشخيص أو خطة يكتبها الطبيب أو الطاقم يدويا.",
                    "instructions": "تعليمات يكتبها الطبيب أو الطاقم يدويا.",
                    "follow_up_notes": "ملاحظات متابعة يكتبها الطبيب أو الطاقم يدويا.",
                    "is_visible_to_patient": "يظل السجل خاصا ما لم يتم تفعيل هذا الخيار.",
                },
                "en": {
                    "doctor_notes": "Manual content entered by the doctor or staff.",
                    "diagnosis_plan": "A diagnosis or plan entered manually by the doctor or staff.",
                    "instructions": "Instructions entered manually by the doctor or staff.",
                    "follow_up_notes": "Follow-up notes entered manually by the doctor or staff.",
                    "is_visible_to_patient": "The record remains private unless this is selected.",
                },
            },
        )


class StaffClinicalNoteForm(_LocalizedRecordFormMixin, forms.ModelForm):
    class Meta:
        model = ClinicalNote
        fields = [
            "visit",
            "note_type",
            "title",
            "body",
            "is_visible_to_patient",
        ]
        labels = {
            "visit": "الزيارة المرتبطة",
            "note_type": "نوع الملاحظة",
            "title": "العنوان",
            "body": "نص الملاحظة",
            "is_visible_to_patient": "ظاهر للمريض",
        }
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, patient, created_by=None, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.created_by = created_by
        self.instance.patient = patient
        self.instance.created_by = created_by
        self.fields["visit"].required = False
        self.fields["visit"].empty_label = _scheduling_copy(
            language,
            "بدون زيارة مرتبطة",
            "No linked visit",
        )
        self.fields["visit"].queryset = VisitRecord.objects.filter(patient=patient).order_by(
            "-visit_date",
            "-created_at",
        )
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "visit": "الزيارة المرتبطة",
                    "note_type": "نوع الملاحظة",
                    "title": "العنوان",
                    "body": "نص الملاحظة",
                    "is_visible_to_patient": "ظاهر للمريض",
                },
                "en": {
                    "visit": "Linked visit",
                    "note_type": "Note type",
                    "title": "Title",
                    "body": "Note body",
                    "is_visible_to_patient": "Visible to patient",
                },
            },
            help_texts={
                "ar": {
                    "body": "ملاحظة يكتبها الطبيب أو الطاقم يدويا.",
                    "is_visible_to_patient": "تظل الملاحظة خاصة ما لم يتم تفعيل هذا الخيار.",
                },
                "en": {
                    "body": "A note entered manually by the doctor or staff.",
                    "is_visible_to_patient": "The note remains private unless this is selected.",
                },
            },
            choices={
                "ar": {"note_type": NOTE_TYPE_CHOICES["ar"]},
                "en": {"note_type": NOTE_TYPE_CHOICES["en"]},
            },
        )


class StaffRecordMediaFolderForm(_LocalizedRecordFormMixin, forms.ModelForm):
    class Meta:
        model = RecordMediaFolder
        fields = ["name"]

    def __init__(self, *args, patient, created_by=None, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.created_by = created_by
        self.instance.patient = patient
        if not self.instance.created_by_id:
            self.instance.created_by = created_by
        self.fields["name"].strip = True
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {"name": "اسم المجلد"},
                "en": {"name": "Folder name"},
            },
        )


class StaffRecordMediaCreateForm(_LocalizedRecordFormMixin, forms.ModelForm):
    class Meta:
        model = RecordMedia
        fields = [
            "visit",
            "folder",
            "media_type",
            "file",
            "content_type",
            "file_size",
            "title",
            "description",
            "visibility",
            "consent_confirmed",
            "is_active",
        ]
        labels = {
            "visit": "الزيارة المرتبطة",
            "folder": "المجلد",
            "media_type": "نوع الملف",
            "file": "ملف خاص",
            "content_type": "نوع المحتوى",
            "file_size": "حجم الملف",
            "title": "العنوان",
            "description": "الوصف",
            "visibility": "حالة الظهور",
            "consent_confirmed": "موافقة مؤكدة",
            "is_active": "نشط",
        }
        widgets = {
            "content_type": forms.HiddenInput(),
            "file_size": forms.HiddenInput(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, patient, uploaded_by=None, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.uploaded_by = uploaded_by
        self.instance.patient = patient
        self.instance.uploaded_by = uploaded_by
        self.fields["visit"].required = False
        self.fields["visit"].empty_label = _scheduling_copy(
            language,
            "بدون زيارة مرتبطة",
            "No linked visit",
        )
        self.fields["visit"].queryset = VisitRecord.objects.filter(patient=patient).order_by(
            "-visit_date",
            "-created_at",
        )
        self.fields["folder"].required = False
        self.fields["folder"].empty_label = _scheduling_copy(
            language,
            "بدون مجلد",
            "Unfiled",
        )
        self.fields["folder"].queryset = RecordMediaFolder.objects.filter(patient=patient)
        self.fields["content_type"].required = False
        self.fields["file_size"].required = False
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "visit": "الزيارة المرتبطة",
                    "folder": "المجلد",
                    "media_type": "نوع الملف",
                    "file": "ملف خاص",
                    "content_type": "نوع المحتوى",
                    "file_size": "حجم الملف",
                    "title": "العنوان",
                    "description": "الوصف",
                    "visibility": "حالة الظهور",
                    "consent_confirmed": "موافقة مؤكدة",
                    "is_active": "نشط",
                },
                "en": {
                    "visit": "Linked visit",
                    "folder": "Folder",
                    "media_type": "Media type",
                    "file": "Private media file",
                    "content_type": "Content type",
                    "file_size": "File size",
                    "title": "Title",
                    "description": "Description",
                    "visibility": "Visibility",
                    "consent_confirmed": "Confirmed consent",
                    "is_active": "Active",
                },
            },
            help_texts={
                "ar": {
                    "visibility": "ظاهر للمريض لا يعني أن الملف عام.",
                    "consent_confirmed": "مطلوبة فقط عند اعتماد الملف كحالة عامة.",
                },
                "en": {
                    "visibility": "Visible to patient does not mean public.",
                    "consent_confirmed": "Required only for an approved public case.",
                },
            },
            choices={
                "ar": {
                    "media_type": MEDIA_TYPE_CHOICES["ar"],
                    "visibility": PRIVATE_MEDIA_VISIBILITY_CHOICES["ar"],
                },
                "en": {
                    "media_type": MEDIA_TYPE_CHOICES["en"],
                    "visibility": PRIVATE_MEDIA_VISIBILITY_CHOICES["en"],
                },
            },
        )


class StaffPublicCaseCreateForm(_LocalizedRecordFormMixin, forms.Form):
    reference_visit = forms.ModelChoiceField(
        queryset=VisitRecord.objects.none(),
        required=False,
    )
    folder = forms.ModelChoiceField(
        queryset=RecordMediaFolder.objects.none(),
        required=False,
    )
    case_title = forms.CharField(
        required=True,
        max_length=PUBLIC_CASE_TITLE_MAX_LENGTH,
        strip=True,
        widget=forms.TextInput(attrs={"maxlength": str(PUBLIC_CASE_TITLE_MAX_LENGTH)}),
    )
    before_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"}
        ),
    )
    after_images = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"}
        ),
    )
    videos = MultipleFileField(
        required=False,
        widget=MultipleFileInput(attrs={"accept": "video/mp4,.mp4"}),
    )
    video_cover = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"}
        ),
    )
    short_note = forms.CharField(
        required=False,
        max_length=PUBLIC_CASE_NOTE_MAX_LENGTH,
        strip=True,
        widget=forms.Textarea(
            attrs={"rows": 3, "maxlength": str(PUBLIC_CASE_NOTE_MAX_LENGTH)}
        ),
    )
    consent_confirmed = forms.BooleanField(required=True)

    def __init__(
        self,
        *args,
        patient,
        uploaded_by,
        public_case=None,
        language="ar",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.uploaded_by = uploaded_by
        self.public_case = public_case
        self.media_instances = []
        self.media_specs = []
        self.fields["reference_visit"].queryset = VisitRecord.objects.filter(
            patient=patient
        ).order_by(
            "-visit_date",
            "-created_at",
        )
        self.fields["reference_visit"].empty_label = _scheduling_copy(
            language,
            "بدون زيارة مرجعية",
            "No reference visit",
        )
        self.fields["folder"].queryset = RecordMediaFolder.objects.filter(patient=patient)
        self.fields["folder"].empty_label = _scheduling_copy(
            language,
            "بدون مجلد",
            "Unfiled",
        )
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "reference_visit": "الزيارة المرجعية (اختياري)",
                    "folder": "المجلد (اختياري)",
                    "case_title": "عنوان الحالة",
                    "before_images": "صور قبل",
                    "after_images": "صور بعد",
                    "videos": "فيديوهات",
                    "video_cover": "غلاف الفيديو (اختياري)",
                    "short_note": "ملاحظة عامة قصيرة (اختياري)",
                    "consent_confirmed": (
                        "أؤكد أن موافقة المريض على النشر تم الحصول عليها في العيادة."
                    ),
                },
                "en": {
                    "reference_visit": "Reference visit (optional)",
                    "folder": "Folder (optional)",
                    "case_title": "Case title",
                    "before_images": "Before images",
                    "after_images": "After images",
                    "videos": "Videos",
                    "video_cover": "Video cover image (optional)",
                    "short_note": "Short public note (optional)",
                    "consent_confirmed": (
                        "I confirm that the patient's consent for public display was obtained "
                        "in the clinic."
                    ),
                },
            },
            help_texts={
                "ar": {
                    "reference_visit": (
                        "للتنظيم الداخلي فقط، ولا تحدد كيفية تجميع الحالة في الموقع."
                    ),
                    "case_title": (
                        "سيظهر هذا العنوان للزوار. لا تكتب اسم المريض أو أي معلومات تعريفية."
                    ),
                    "short_note": (
                        "تظهر هذه الملاحظة للزوار. لا تكتب اسم المريض أو رقم الهاتف أو أي "
                        "معلومات طبية خاصة."
                    ),
                },
                "en": {
                    "reference_visit": (
                        "For internal record context only. It does not determine public case "
                        "grouping."
                    ),
                    "case_title": (
                        "This title is public. Do not enter the patient's name or identifying "
                        "information."
                    ),
                    "short_note": (
                        "This note is visible to visitors. Do not enter the patient's name, "
                        "phone number, or private medical information."
                    ),
                },
            },
        )
        for field_name in ("case_title", "short_note"):
            if field_name not in self.fields:
                continue
            for validator in self.fields[field_name].validators:
                if getattr(validator, "code", "") == "max_length":
                    validator.message = RECORD_FIELD_ERROR_MESSAGES[self.language]["max_length"]

    def _localized_model_error(self, message):
        if self.language == "ar":
            return RECORD_MODEL_ERROR_TRANSLATIONS_AR.get(message, message)
        return message

    def _add_media_validation_errors(self, field_name, error):
        if hasattr(error, "message_dict"):
            messages = [
                message
                for field_messages in error.message_dict.values()
                for message in field_messages
            ]
        else:
            messages = error.messages
        for message in messages:
            self.add_error(field_name, self._localized_model_error(message))

    def clean(self):
        cleaned_data = super().clean()
        before_images = cleaned_data.get("before_images") or []
        after_images = cleaned_data.get("after_images") or []
        videos = cleaned_data.get("videos") or []
        video_cover = cleaned_data.get("video_cover")
        actual_media_count = len(before_images) + len(after_images) + len(videos)
        existing_video = bool(
            self.public_case
            and self.public_case.media_items.filter(
                public_case_role=RecordMedia.PublicCaseRole.VIDEO,
                media_type=RecordMedia.MediaType.SHORT_VIDEO,
                is_active=True,
            ).exists()
        )
        cover_only_replacement = bool(video_cover and existing_video)
        if not actual_media_count and not cover_only_replacement:
            self.add_error(
                None,
                _scheduling_copy(
                    self.language,
                    "أضف صورة قبل أو صورة بعد أو فيديو واحداً على الأقل.",
                    "Add at least one before image, after image, or video.",
                ),
            )
        if video_cover and not videos and not existing_video:
            self.add_error(
                "video_cover",
                _scheduling_copy(
                    self.language,
                    "لا يمكن إضافة غلاف فيديو بدون إضافة فيديو.",
                    "A video cover requires at least one video.",
                ),
            )

        pii_error = _scheduling_copy(
            self.language,
            "لا يمكن نشر اسم المريض أو رقم هاتفه ضمن المحتوى العام.",
            "The patient's name or phone number cannot be published in public content.",
        )
        for field_name in ("case_title", "short_note"):
            if field_name not in self.fields:
                continue
            value = cleaned_data.get(field_name, "")
            if value and _contains_current_patient_pii(value, self.patient):
                self.add_error(field_name, pii_error)

        reference_visit = cleaned_data.get("reference_visit")
        case_title = cleaned_data.get("case_title", "")
        requires_case_metadata = "case_title" in self.fields
        if requires_case_metadata and (
            not case_title or not cleaned_data.get("consent_confirmed")
        ):
            return cleaned_data
        if not actual_media_count and not cover_only_replacement:
            return cleaned_data

        folder = cleaned_data.get("folder")
        media_specs = []
        media_specs.extend(
            ("before_images", RecordMedia.MediaType.IMAGE, PUBLIC_CASE_ROLE_BEFORE, item)
            for item in before_images
        )
        media_specs.extend(
            ("after_images", RecordMedia.MediaType.IMAGE, PUBLIC_CASE_ROLE_AFTER, item)
            for item in after_images
        )
        media_specs.extend(
            ("videos", RecordMedia.MediaType.SHORT_VIDEO, PUBLIC_CASE_ROLE_VIDEO, item)
            for item in videos
        )
        if video_cover:
            media_specs.append(
                (
                    "video_cover",
                    RecordMedia.MediaType.IMAGE,
                    PUBLIC_CASE_ROLE_VIDEO_COVER,
                    video_cover,
                )
            )

        media_instances = []
        for field_name, media_type, role, uploaded_file in media_specs:
            media = RecordMedia(
                patient=self.patient,
                visit=reference_visit,
                folder=folder,
                media_type=media_type,
                file=uploaded_file,
                title="",
                description="",
                visibility=RecordMedia.Visibility.PRIVATE_ONLY,
                consent_confirmed=False,
                is_active=True,
                uploaded_by=self.uploaded_by,
            )
            try:
                media.full_clean()
            except ValidationError as error:
                self._add_media_validation_errors(field_name, error)
            media_instances.append(media)

        if not self.errors:
            self.media_instances = media_instances
            self.media_specs = media_specs
        return cleaned_data

    def build_media_instances(self, public_case):
        if not self.is_valid():
            raise ValueError("Cannot build public case media from an invalid form.")
        instances = []
        for media, media_spec in zip(self.media_instances, self.media_specs, strict=True):
            media.public_case = public_case
            media.public_case_role = media_spec[2]
            media.visibility = RecordMedia.Visibility.APPROVED_PUBLIC_CASE
            media.consent_confirmed = True
            media.full_clean()
            instances.append(media)
        return instances


class StaffPublicCaseAddMediaForm(StaffPublicCaseCreateForm):
    def __init__(self, *args, public_case, **kwargs):
        super().__init__(*args, public_case=public_case, **kwargs)
        self.fields.pop("case_title")
        self.fields.pop("short_note")
        self.fields.pop("consent_confirmed")


class StaffPublicCaseUpdateForm(_LocalizedRecordFormMixin, forms.ModelForm):
    class Meta:
        model = PublicCase
        fields = ["title", "note", "reference_visit"]
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": str(PUBLIC_CASE_TITLE_MAX_LENGTH)}),
            "note": forms.Textarea(
                attrs={"rows": 3, "maxlength": str(PUBLIC_CASE_NOTE_MAX_LENGTH)}
            ),
        }

    def __init__(self, *args, patient, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.instance.patient = patient
        self.fields["title"].required = True
        self.fields["title"].strip = True
        self.fields["note"].required = False
        self.fields["note"].strip = True
        self.fields["note"].validators = [
            validator
            for validator in forms.CharField(max_length=PUBLIC_CASE_NOTE_MAX_LENGTH).validators
        ]
        self.fields["reference_visit"].required = False
        self.fields["reference_visit"].queryset = VisitRecord.objects.filter(
            patient=patient
        ).order_by("-visit_date", "-created_at")
        self.fields["reference_visit"].empty_label = _scheduling_copy(
            language,
            "بدون زيارة مرجعية",
            "No reference visit",
        )
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "title": "عنوان الحالة",
                    "note": "ملاحظة عامة قصيرة (اختياري)",
                    "reference_visit": "الزيارة المرجعية (اختياري)",
                },
                "en": {
                    "title": "Case title",
                    "note": "Short public note (optional)",
                    "reference_visit": "Reference visit (optional)",
                },
            },
            help_texts={
                "ar": {
                    "title": (
                        "سيظهر هذا العنوان للزوار. لا تكتب اسم المريض أو أي معلومات تعريفية."
                    ),
                    "note": (
                        "تظهر هذه الملاحظة للزوار. لا تكتب اسم المريض أو رقم الهاتف أو أي "
                        "معلومات طبية خاصة."
                    ),
                    "reference_visit": (
                        "للتنظيم الداخلي فقط، ولا تحدد كيفية تجميع الحالة في الموقع."
                    ),
                },
                "en": {
                    "title": (
                        "This title is public. Do not enter the patient's name or identifying "
                        "information."
                    ),
                    "note": (
                        "This note is visible to visitors. Do not enter the patient's name, "
                        "phone number, or private medical information."
                    ),
                    "reference_visit": (
                        "For internal record context only. It does not determine public case "
                        "grouping."
                    ),
                },
            },
        )

    def clean(self):
        cleaned_data = super().clean()
        pii_error = _scheduling_copy(
            self.language,
            "لا يمكن نشر اسم المريض أو رقم هاتفه ضمن المحتوى العام.",
            "The patient's name or phone number cannot be published in public content.",
        )
        for field_name in ("title", "note"):
            value = cleaned_data.get(field_name, "")
            if value and _contains_current_patient_pii(value, self.patient):
                self.add_error(field_name, pii_error)
        return cleaned_data


class StaffPublicCaseMergeForm(_LocalizedRecordFormMixin, forms.Form):
    destination_case = forms.ModelChoiceField(queryset=PublicCase.objects.none())

    def __init__(self, *args, patient, source_case, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination_case"].queryset = PublicCase.objects.filter(
            patient=patient
        ).exclude(pk=source_case.pk)
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {"destination_case": "الحالة الوجهة"},
                "en": {"destination_case": "Destination case"},
            },
            help_texts={
                "ar": {
                    "destination_case": "ستبقى بيانات الحالة الوجهة هي المعتمدة."
                },
                "en": {
                    "destination_case": "The destination case metadata remains authoritative."
                },
            },
        )


class StaffRecordMediaUpdateForm(_LocalizedRecordFormMixin, forms.ModelForm):
    class Meta:
        model = RecordMedia
        fields = [
            "folder",
            "title",
            "description",
            "visibility",
            "consent_confirmed",
            "is_active",
        ]
        labels = {
            "folder": "المجلد",
            "title": "العنوان",
            "description": "الوصف",
            "visibility": "حالة الظهور",
            "consent_confirmed": "موافقة مؤكدة",
            "is_active": "نشط",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, patient, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["folder"].required = False
        self.fields["folder"].empty_label = _scheduling_copy(
            language,
            "بدون مجلد",
            "Unfiled",
        )
        self.fields["folder"].queryset = RecordMediaFolder.objects.filter(patient=patient)
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "folder": "المجلد",
                    "title": "العنوان",
                    "description": "الوصف",
                    "visibility": "حالة الظهور",
                    "consent_confirmed": "موافقة مؤكدة",
                    "is_active": "نشط",
                },
                "en": {
                    "folder": "Folder",
                    "title": "Title",
                    "description": "Description",
                    "visibility": "Visibility",
                    "consent_confirmed": "Confirmed consent",
                    "is_active": "Active",
                },
            },
            help_texts={
                "ar": {
                    "visibility": "ظاهر للمريض لا يعني أن الملف عام.",
                    "consent_confirmed": "مطلوبة عند اعتماد الملف كحالة عامة.",
                },
                "en": {
                    "visibility": "Visible to patient does not mean public.",
                    "consent_confirmed": "Required for an approved public case.",
                },
            },
            choices={
                "ar": {"visibility": PRIVATE_MEDIA_VISIBILITY_CHOICES["ar"]},
                "en": {"visibility": PRIVATE_MEDIA_VISIBILITY_CHOICES["en"]},
            },
        )
        if self.instance.public_case_id:
            self.fields.pop("visibility")
            self.fields.pop("consent_confirmed")
