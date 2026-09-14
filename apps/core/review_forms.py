from django import forms
from django.core import signing
from django.utils.translation import get_language

from . import review_moderation
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
        if review_moderation.is_patient_review(self.instance):
            # ModelAdmin generates a new Meta.fields containing review_version.
            # Remove only model controls; keep the signed revision field intact.
            for name in ("is_approved_for_publication", "is_active", "is_featured", "display_order"):
                self.fields.pop(name, None)
        if self.instance.pk:
            self.initial["review_version"] = review_moderation.sign_review_revision(
                self.instance, salt=self.version_salt,
            )

    def clean(self):
        cleaned_data = super().clean()
        token = cleaned_data.get("review_version")
        if not token or not self.instance.pk:
            return cleaned_data
        # Both admin change views run inside a transaction. Keep this lock until
        # moderation is saved so a patient edit cannot slip past this check.
        current = (
            PublicReview.objects.using(self.instance._state.db)
            .select_for_update().filter(pk=self.instance.pk).first()
        )
        try:
            review_moderation.validate_review_revision(token, current, salt=self.version_salt)
        except signing.BadSignature:
            raise forms.ValidationError("Reload this review before moderating it.") from None
        except review_moderation.StaleReviewRevision:
            raise forms.ValidationError(
                "This review changed after you opened it. Reload and read the latest review before moderating it."
            ) from None
        if review_moderation.is_patient_review(current):
            action = self.data.get("moderation_action")
            if action not in review_moderation.VISIBILITY_ACTIONS:
                raise forms.ValidationError(
                    "اختر إخفاء أو إظهار." if (get_language() or "").startswith("ar")
                    else "Choose Hide or Show."
                )
            cleaned_data["moderation_action"] = action
        return cleaned_data


class ReviewListModerationForm(ReviewModerationForm):
    """Keep imported inline edits; patient reviews use their detail actions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if review_moderation.is_patient_review(self.instance):
            self.fields.pop("review_version", None)
