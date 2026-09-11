"""Session-bound account OTP state, with database-atomic verification and reset.

No account exists until registration verification. Only password/OTP hashes are
stored. Expiry never slides on failed verification or resend. The database is
authoritative; the shared cache is used only for fail-closed rate limiting.
"""

import re
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.debug import sensitive_variables

from apps.booking.rate_limits import get_client_ip
from .models import AccountOtpChallenge, Patient
from .otp import (
    WhatsAppOtpServiceUnavailable,
    generate_otp_code,
    send_patient_account_otp,
)
from . import rate_limits

OTP_TTL_SECONDS = 600
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
RECOVERY_GRANT_TTL_SECONDS = 600
OTP_RE = re.compile(r"[0-9]{6}")
SESSION_BINDING_KEY = "patient_account_otp_binding"
REGISTRATION_SESSION_KEY = "patient_registration_otp_challenge"
RECOVERY_SESSION_KEY = "patient_recovery_otp_challenge"
SESSION_KEYS = {
    "registration": REGISTRATION_SESSION_KEY,
    "recovery": RECOVERY_SESSION_KEY,
}


def _digest(value):
    return salted_hmac("patient-account-otp", value, algorithm="sha256").hexdigest()


def _binding(request):
    value = request.session.get(SESSION_BINDING_KEY, "")
    return _digest(value) if value else ""


def allow_request(request, *, scope, phone="", limit=20, window=3600):
    """Independent IP and phone limits; changing either cannot reset the other."""
    identities = [("ip", get_client_ip(request))]
    if phone:
        identities.append(("phone", phone))
    try:
        allowed = True
        for kind, identity in identities:
            key = f"account-otp-rate:{scope}:{kind}:{_digest(identity)}"
            count = 1 if cache.add(key, 1, timeout=window) else cache.incr(key)
            allowed = allowed and count <= limit
        return allowed
    except Exception:
        return False


def registration_allowed(request, phone):
    try:
        return rate_limits.check_registration_attempt_rate_limit(
            request,
            normalized_phone=phone,
        ).allowed
    except Exception:
        return False


def challenge_for(request, purpose, *, lock=False):
    token = request.session.get(SESSION_KEYS[purpose])
    if not token or not _binding(request):
        return None
    query = AccountOtpChallenge.objects
    if lock:
        query = query.select_for_update()
    try:
        return query.filter(
            pk=token, purpose=purpose, session_digest=_binding(request)
        ).first()
    except (ValidationError, ValueError, TypeError):
        return None


def available(challenge):
    return bool(
        challenge
        and not challenge.verified_at
        and challenge.expires_at > timezone.now()
        and challenge.attempt_count < OTP_MAX_ATTEMPTS
    )


def _eligible_user(phone):
    return (
        get_user_model()
        .objects.filter(
            username=phone,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        .first()
    )


def _phone_taken(phone):
    # Unlinked booking records are not accounts and never grant portal access.
    return (
        get_user_model().objects.filter(username=phone).exists()
        or Patient.objects.filter(phone_e164=phone, user__isnull=False).exists()
    )


@sensitive_variables()
def _send(challenge):
    code = generate_otp_code()
    challenge.otp_digest = make_password(code)
    challenge.last_sent_at = timezone.now()
    try:
        if not cache.add(
            f"account-otp-cooldown:{_digest(challenge.phone_e164)}",
            True,
            timeout=OTP_RESEND_COOLDOWN_SECONDS,
        ):
            raise WhatsAppOtpServiceUnavailable()
        # Send the same neutral OTP for any syntactically valid phone. Account
        # eligibility is checked only after proof of phone possession, avoiding
        # response and provider-latency differences for arbitrary account probes.
        send_patient_account_otp(challenge.phone_e164, code, challenge.language)
    except Exception:
        challenge.otp_digest = ""  # Even a generated code cannot verify a failed send.
    challenge.save()


@sensitive_variables()
def start(request, purpose, phone, language, *, registration=None):
    now = timezone.now()
    # Expired state contains temporary registration details; remove it on starts.
    AccountOtpChallenge.objects.filter(expires_at__lte=now).filter(
        Q(grant_expires_at__isnull=True) | Q(grant_expires_at__lte=now)
    ).delete()
    if not request.session.get(SESSION_BINDING_KEY):
        request.session[SESSION_BINDING_KEY] = secrets.token_urlsafe(32)
    with transaction.atomic():
        old = challenge_for(request, purpose, lock=True)
        if old:
            old.delete()
        user = _eligible_user(phone) if purpose == "recovery" else None
        challenge = AccountOtpChallenge(
            purpose=purpose,
            session_digest=_binding(request),
            phone_e164=phone,
            language=language,
            expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
            pending_registration=registration or {},
            user=user,
            credential_digest=_digest(user.password) if user else "",
        )
        _send(challenge)
    request.session[SESSION_KEYS[purpose]] = str(challenge.pk)
    return challenge


def resend(request, purpose):
    with transaction.atomic():
        challenge = challenge_for(request, purpose, lock=True)
        if not available(challenge):
            return "expired"
        if (
            challenge.last_sent_at
            and (timezone.now() - challenge.last_sent_at).total_seconds()
            < OTP_RESEND_COOLDOWN_SECONDS
        ):
            return "cooldown"
        if not allow_request(
            request, scope="send", phone=challenge.phone_e164, limit=6
        ):
            return "limited"
        _send(challenge)
        # Neither expiry nor the total verification attempt budget is reset.
        return "sent"


@sensitive_variables()
def verify(request, purpose, code):
    with transaction.atomic():
        challenge = challenge_for(request, purpose, lock=True)
        if not available(challenge):
            return None
        challenge.attempt_count += 1
        challenge.save(update_fields=["attempt_count"])
        if not (
            isinstance(code, str)
            and OTP_RE.fullmatch(code)
            and challenge.otp_digest
            and check_password(code, challenge.otp_digest)
        ):
            return None
        if purpose == "registration":
            data = challenge.pending_registration
            if _phone_taken(challenge.phone_e164):
                challenge.delete()
                return None
            try:
                with transaction.atomic():
                    user = get_user_model().objects.create(
                        username=challenge.phone_e164,
                        password=data["password_hash"],
                        first_name=data["full_name"][:150],
                        email=data["email"],
                        is_active=True,
                        is_staff=False,
                        is_superuser=False,
                    )
            except IntegrityError:
                challenge.delete()
                return None
            next_url = data.get("next_url", "")
            challenge.delete()
            request.session.pop(REGISTRATION_SESSION_KEY, None)
            return user, next_url
        user = _eligible_user(challenge.phone_e164)
        if (
            not user
            or user.pk != challenge.user_id
            or _digest(user.password) != challenge.credential_digest
        ):
            challenge.delete()
            return None
        challenge.verified_at = timezone.now()
        challenge.grant_expires_at = challenge.verified_at + timedelta(
            seconds=RECOVERY_GRANT_TTL_SECONDS
        )
        challenge.otp_digest = ""
        challenge.save(update_fields=["verified_at", "grant_expires_at", "otp_digest"])
        return user


def recovery_user(challenge, *, lock=False):
    if (
        not challenge
        or not challenge.verified_at
        or challenge.grant_expires_at <= timezone.now()
    ):
        return None
    query = get_user_model().objects
    if lock:
        query = query.select_for_update()
    user = query.filter(
        pk=challenge.user_id,
        username=challenge.phone_e164,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    ).first()
    if user and _digest(user.password) == challenge.credential_digest:
        return user
    return None


@sensitive_variables()
def reset_password(request, data, form_class, language):
    """Lock both grant and user; another reset/password change invalidates this grant."""
    with transaction.atomic():
        challenge = challenge_for(request, "recovery", lock=True)
        user = recovery_user(challenge, lock=True)
        if user is None:
            return None, False
        form = form_class(user, data, language)
        if not form.is_valid():
            return form, False
        form.save()
        challenge.delete()
        request.session.pop(RECOVERY_SESSION_KEY, None)
        return form, True
