from django import forms

from apps.core.models import PublicReview


class PatientReviewForm(forms.ModelForm):
    # Explicit choice for the public display of the alias, stars and review text.
    # It is deliberately not a model field and is never initially checked.
    publication_consent = forms.BooleanField(required=True, initial=False)

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
        self.fields["publication_consent"].label = (
            "أوافق على نشر الاسم الظاهر الذي اخترته (أو «مريض»)، والنجوم، ونص تقييمي "
            "للعامة على موقع العيادة. أستطيع إيقاف النشر من حسابي لاحقًا."
            if arabic else
            'I agree to publish my chosen display name (or "Patient"), star rating, '
            "and review text publicly on the clinic website. I can stop publication "
            "from my account later."
        )
        self.fields["publication_consent"].error_messages["required"] = (
            "يجب اختيار الموافقة على النشر قبل نشر التقييم."
            if arabic else
            "Select publication consent before publishing your review."
        )
