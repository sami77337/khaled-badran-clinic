from django import forms
from django.core import signing
from django.utils.translation import get_language


class PatientReviewActionForm(forms.Form):
    """Bind one action to the revision displayed on its review/confirmation page.

    POST callers must obtain the review under a row lock and retain the lock
    through validation and save/delete. Tokens cannot authorize a different action.
    """

    review_version = forms.CharField(widget=forms.HiddenInput)
    version_salt = "dashboard.patient-review-action"

    def __init__(self, *args, review, action, **kwargs):
        kwargs.setdefault("auto_id", False)
        super().__init__(*args, **kwargs)
        self.revision = {
            "id": review.pk, "updated_at": review.updated_at.isoformat(), "action": action,
        }
        self.initial["review_version"] = signing.Signer(salt=self.version_salt).sign_object(self.revision)
        self.fields["review_version"].error_messages["required"] = self.reload_message

    @property
    def reload_message(self):
        return (
            "أعد تحميل التقييم واقرأ أحدث نسخة قبل المتابعة."
            if (get_language() or "").startswith("ar")
            else "Reload the review and read the latest version before continuing."
        )

    def clean_review_version(self):
        token = self.cleaned_data["review_version"]
        try:
            revision = signing.Signer(salt=self.version_salt).unsign_object(token)
        except signing.BadSignature:
            raise forms.ValidationError(self.reload_message) from None
        if revision != self.revision:
            raise forms.ValidationError(self.reload_message)
        return token
