"""Shared review integrity and patient moderation rules for staff surfaces.

Callers own permissions, CSRF and transactions. For writes, validate the locked
current review and retain its row lock through the transition/delete and audit.
"""

from django.core import signing
from django.core.exceptions import PermissionDenied

from .models import PublicReview


VISIBILITY_ACTIONS = frozenset({"hide", "show"})


class StaleReviewRevision(ValueError):
    """The displayed review no longer matches the current database revision."""


def is_patient_review(review):
    return review.source == PublicReview.Source.PATIENT_PORTAL


def patient_reviews(queryset=None):
    if queryset is None:
        queryset = PublicReview.objects.all()
    return queryset.filter(source=PublicReview.Source.PATIENT_PORTAL)


def _revision(review, *, action=None):
    revision = {"id": review.pk, "updated_at": review.updated_at.isoformat()}
    if action is not None:
        revision["action"] = action
    return revision


def sign_review_revision(review, *, salt, action=None):
    return signing.Signer(salt=salt).sign_object(_revision(review, action=action))


def validate_review_revision(token, review, *, salt, action=None):
    """Raise BadSignature or StaleReviewRevision; also supports imported admin edits."""
    revision = signing.Signer(salt=salt).unsign_object(token)
    if review is None or revision != _revision(review, action=action):
        raise StaleReviewRevision


def set_patient_review_visibility(review, action):
    """Save only visibility fields on an already locked, revision-validated row."""
    if not is_patient_review(review) or action not in VISIBILITY_ACTIONS:
        raise PermissionDenied
    review.is_approved_for_publication = action == "show"
    fields = ["is_approved_for_publication", "updated_at"]
    if action == "show":
        # Show also restores reviews deactivated by the legacy UI.
        review.is_active = True
        fields.append("is_active")
    review.save(update_fields=fields)
