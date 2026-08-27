from django import forms
from django.core.exceptions import ValidationError

from apps.booking.models import Appointment
from apps.clinic.models import ClosedDay, DoctorSchedule, DoctorScheduleOverride, VisitType
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord


DATETIME_INPUT_FORMATS = [
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
]

TIME_INPUT_FORMATS = ["%H:%M"]
MAX_VISIT_DURATION_MINUTES = 65_535
MAX_BOOKING_HORIZON_DAYS = 3_650
MAX_BOOKING_RULE_MINUTES = 5_256_000

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

MEDIA_VISIBILITY_CHOICES = {
    "ar": (
        (RecordMedia.Visibility.PRIVATE_ONLY, "خاص فقط"),
        (RecordMedia.Visibility.VISIBLE_TO_PATIENT, "ظاهر للمريض"),
        (RecordMedia.Visibility.APPROVED_PUBLIC_CASE, "حالة عامة بموافقة"),
    ),
    "en": RecordMedia.Visibility.choices,
}


def _scheduling_copy(language, arabic, english):
    return english if language == "en" else arabic


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


class StaffRecordMediaCreateForm(_LocalizedRecordFormMixin, forms.ModelForm):
    class Meta:
        model = RecordMedia
        fields = [
            "visit",
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
        self.fields["content_type"].required = False
        self.fields["file_size"].required = False
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "visit": "الزيارة المرتبطة",
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
                    "visibility": MEDIA_VISIBILITY_CHOICES["ar"],
                },
                "en": {
                    "media_type": MEDIA_TYPE_CHOICES["en"],
                    "visibility": MEDIA_VISIBILITY_CHOICES["en"],
                },
            },
        )


class StaffRecordMediaUpdateForm(_LocalizedRecordFormMixin, forms.ModelForm):
    class Meta:
        model = RecordMedia
        fields = [
            "title",
            "description",
            "visibility",
            "consent_confirmed",
            "is_active",
        ]
        labels = {
            "title": "العنوان",
            "description": "الوصف",
            "visibility": "حالة الظهور",
            "consent_confirmed": "موافقة مؤكدة",
            "is_active": "نشط",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        self._configure_record_localization(
            language=language,
            labels={
                "ar": {
                    "title": "العنوان",
                    "description": "الوصف",
                    "visibility": "حالة الظهور",
                    "consent_confirmed": "موافقة مؤكدة",
                    "is_active": "نشط",
                },
                "en": {
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
                "ar": {"visibility": MEDIA_VISIBILITY_CHOICES["ar"]},
                "en": {"visibility": MEDIA_VISIBILITY_CHOICES["en"]},
            },
        )
