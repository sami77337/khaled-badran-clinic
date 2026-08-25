from django import forms

from apps.booking.models import Appointment
from apps.clinic.models import ClosedDay, DoctorSchedule, DoctorScheduleOverride
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


def _scheduling_copy(language, arabic, english):
    return english if language == "en" else arabic


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
            "booking_max_days_ahead": ("أقصى مدة للحجز المسبق", "Maximum booking horizon"),
            "booking_slot_interval_minutes": ("الفاصل بين أوقات الحجز", "Slot interval"),
            "appointment_reminder_offset_minutes": (
                "وقت التذكير قبل الموعد",
                "Appointment reminder lead time",
            ),
        }
        units = {
            "booking_enabled": ("مفعل أو غير مفعل", "Enabled or disabled"),
            "booking_min_lead_minutes": ("بالدقائق", "Minutes"),
            "booking_max_days_ahead": ("بالأيام", "Days"),
            "booking_slot_interval_minutes": ("بالدقائق", "Minutes"),
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


class StaffVisitRecordForm(forms.ModelForm):
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

    def __init__(self, *args, patient, **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.instance.patient = patient
        self.fields["appointment"].required = False
        self.fields["appointment"].empty_label = "بدون موعد مرتبط"
        self.fields["appointment"].queryset = (
            Appointment.objects.filter(patient=patient)
            .select_related("doctor", "visit_type")
            .order_by("-starts_at", "-id")
        )


class StaffClinicalNoteForm(forms.ModelForm):
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

    def __init__(self, *args, patient, created_by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.created_by = created_by
        self.instance.patient = patient
        self.instance.created_by = created_by
        self.fields["visit"].required = False
        self.fields["visit"].empty_label = "بدون زيارة مرتبطة"
        self.fields["visit"].queryset = VisitRecord.objects.filter(patient=patient).order_by(
            "-visit_date",
            "-created_at",
        )


class StaffRecordMediaCreateForm(forms.ModelForm):
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

    def __init__(self, *args, patient, uploaded_by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.patient = patient
        self.uploaded_by = uploaded_by
        self.instance.patient = patient
        self.instance.uploaded_by = uploaded_by
        self.fields["visit"].required = False
        self.fields["visit"].empty_label = "بدون زيارة مرتبطة"
        self.fields["visit"].queryset = VisitRecord.objects.filter(patient=patient).order_by(
            "-visit_date",
            "-created_at",
        )
        self.fields["content_type"].required = False
        self.fields["file_size"].required = False


class StaffRecordMediaUpdateForm(forms.ModelForm):
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
