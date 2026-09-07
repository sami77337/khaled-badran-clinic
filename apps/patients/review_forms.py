from django import forms

from apps.core.models import PublicReview


class PatientReviewForm(forms.ModelForm):
    class Meta:
        model = PublicReview
        fields = ("reviewer_name", "rating", "body")
        widgets = {
            "reviewer_name": forms.TextInput(attrs={"autocomplete": "off"}),
            "body": forms.Textarea(attrs={"class": "patient-textarea", "rows": 6}),
        }

    def __init__(self, *args, language="ar", **kwargs):
        super().__init__(*args, **kwargs)
        arabic = language == "ar"
        self.fields["reviewer_name"].label = "الاسم الظاهر (اختياري)" if arabic else "Display name (optional)"
        self.fields["reviewer_name"].help_text = (
            "اتركه فارغًا للظهور باسم «مريض». لا تُدرج بيانات اتصال أو معلومات طبية في الاسم أو التقييم."
            if arabic else
            'Leave blank to appear as “Patient”. Do not include contact or medical details in your name or review.'
        )
        self.fields["rating"] = forms.TypedChoiceField(
            coerce=int,
            label="التقييم" if arabic else "Rating",
            choices=[("", "اختر التقييم" if arabic else "Select a rating")]
            + [(value, f"{value} / 5") for value in range(1, 6)],
        )
        self.fields["body"].label = "تقييمك" if arabic else "Your review"
