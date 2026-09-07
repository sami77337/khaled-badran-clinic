from django import forms
from django.core import signing

from .models import PublicReview


class ReviewModerationForm(forms.ModelForm):
    """Bind approval to the exact revision displayed to the moderator."""

    review_version = forms.CharField(widget=forms.HiddenInput)
    version_salt = "core.review-moderation"

    class Meta:
        model = PublicReview
        fields = (
            "is_approved_for_publication", "is_active", "is_featured", "display_order",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["review_version"] = signing.Signer(salt=self.version_salt).sign_object(
                self._revision(self.instance),
            )

    @staticmethod
    def _revision(review):
        return {"id": review.pk, "updated_at": review.updated_at.isoformat()}

    def clean(self):
        cleaned_data = super().clean()
        token = cleaned_data.get("review_version")
        if not token or not self.instance.pk:
            return cleaned_data
        try:
            revision = signing.Signer(salt=self.version_salt).unsign_object(token)
        except signing.BadSignature:
            raise forms.ValidationError("Reload this review before moderating it.") from None

        # Both admin change views run inside a transaction. Keep this lock until
        # moderation is saved so a patient edit cannot slip past this check.
        current = (
            PublicReview.objects.using(self.instance._state.db)
            .select_for_update().filter(pk=self.instance.pk).first()
        )
        if current is None or revision != self._revision(current):
            raise forms.ValidationError(
                "This review changed after you opened it. Reload and read the latest review before moderating it."
            )
        return cleaned_data
