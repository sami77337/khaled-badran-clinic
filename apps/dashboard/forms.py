from django import forms

from apps.booking.models import Appointment
from apps.records.models import ClinicalNote, RecordMedia, VisitRecord


DATETIME_INPUT_FORMATS = [
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
]


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
