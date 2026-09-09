from functools import wraps

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.views import _base_context
from apps.patients import transient_services as access
from apps.patients.localization import use_page_language
from apps.patients.models import TransientConsultation, TransientConsultationAttachment, TransientConsultationAudioReply
from apps.patients.otp import WhatsAppOtpServiceUnavailable
from apps.patients.transient_forms import GuestConsultationForm, GuestOtpForm, GuestPhoneForm
from apps.patients.views import _consultation_attachment_response, _consultation_status_label
from apps.whatsapp.actions import localized_url


def private_guest_response(view):
    @wraps(view)
    @never_cache
    def wrapped(*args, **kwargs):
        response = view(*args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response
    return wrapped


def _url(language, consultation=None):
    return localized_url("guest_consultation_detail", language, public_id=consultation.public_id) if consultation else localized_url("guest_consultation_entry", language)


def _context(request, language, target=None, **extra):
    context = _base_context(request, "home", language, use_public_shell=True)
    title = "استشارة كزائر" if language == "ar" else "Guest Consultation"
    context.update(
        page_key="guest_consultation", page_title=title, meta_description=title,
        canonical_url=request.build_absolute_uri(_url(language, target)),
        language_switch={"label": "English" if language == "ar" else "العربية",
                         "url": _url("en" if language == "ar" else "ar", target)},
        registered_consultation_url=localized_url("patient_portal_consultation_new", language),
        entry_url=localized_url("guest_consultation_entry", language),
        suppress_whatsapp_quick_link=True,
    )
    context.update(extra)
    return context


COPY = {
    "limited": ("محاولات كثيرة. يرجى الانتظار ثم المحاولة مجددًا.", "Too many attempts. Please wait before trying again."),
    "invalid": ("رمز التحقق غير صحيح أو لم يعد صالحًا.", "The verification code is incorrect or no longer valid."),
    "expired": ("انتهت صلاحية الرمز. اطلب رمزًا جديدًا.", "The code has expired. Request a new code."),
    "unavailable": ("خدمة التحقق عبر واتساب غير متاحة حاليًا. حاول لاحقًا.", "WhatsApp verification is currently unavailable. Please try later."),
    "upload": ("تعذر حفظ الاستشارة والمرفقات. يرجى المحاولة مجددًا.", "The consultation and attachments could not be saved. Please try again."),
    "session_expired": ("يرجى التحقق من رقمك مجددًا قبل إرسال الاستشارة.", "Please verify your number again before submitting a consultation."),
}


@private_guest_response
@sensitive_post_parameters("phone", "code", "question", "display_name")
@require_http_methods(["GET", "POST"])
@use_page_language
def guest_entry(request, language="ar", public_id=None):
    target = get_object_or_404(TransientConsultation, public_id=public_id) if public_id else None
    grant = access.active_grant(request, target)
    if target and grant:
        return _detail(request, target, language)

    challenge = access.pending_challenge(request, target)
    state = "form" if grant else "otp" if challenge else "reverify" if target else "phone"
    status = 200
    error = ""
    phone_form = GuestPhoneForm(language=language)
    otp_form = GuestOtpForm(language=language)
    form = GuestConsultationForm(language=language)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "submit" and grant and target is None:
            form = GuestConsultationForm(request.POST, request.FILES, language=language)
            if not access.check_limit(request, "submit", grant.phone_e164):
                error, status = "limited", 429
            elif form.is_valid():
                try:
                    consultation = access.create_guest_consultation(request, language=language,
                        question=form.cleaned_data["question"], display_name=form.cleaned_data["display_name"],
                        uploaded_files=form.cleaned_data["attachments"],
                    )
                except access.GuestAccessDenied:
                    return redirect(_url(language))
                except (ValidationError, OSError):
                    error = "upload"
                else:
                    request.session["guest_consultation_submitted"] = str(consultation.public_id)
                    return redirect(_url(language, consultation))
        elif action in {"send", "resend"} and not grant:
            if target or (action == "resend" and challenge):
                phone = target.phone_e164 if target else challenge.phone_e164
            else:
                phone_form = GuestPhoneForm(request.POST, language=language)
                phone = phone_form.cleaned_data["phone"] if phone_form.is_valid() else ""
            if phone:
                try:
                    sent = access.start_challenge(request, phone=phone, language=language, consultation=target)
                except WhatsAppOtpServiceUnavailable:
                    error = "unavailable"
                else:
                    if sent is None:
                        error, status = "limited", 429
                    else:
                        return redirect(_url(language, target))
            elif not access.check_limit(request, "send"):
                error, status = "limited", 429
        elif action == "verify" and challenge and not grant:
            otp_form = GuestOtpForm(request.POST, language=language)
            # Malformed codes also count as attempts.
            code = otp_form.cleaned_data["code"] if otp_form.is_valid() else ""
            result = access.verify_challenge(request, challenge=challenge, code=code)
            if result == "verified":
                return redirect(_url(language, target))
            error = result
            status = 429 if result == "limited" else 200
        elif action == "change_phone" and target is None:
            access.challenges(request).update(revoked_at=timezone.now())
            return redirect(_url(language))
        else:
            status = 403
            error = "session_expired" if action == "submit" else "invalid"

    if challenge and challenge.expires_at <= timezone.now() and not error and not grant:
        error = "expired"
    destination = grant.phone_e164 if grant else challenge.phone_e164 if challenge else target.phone_e164 if target else ""
    context = _context(request, language, target, state=state, form=form,
                       phone_form=phone_form, otp_form=otp_form,
                       masked_destination=access.masked_phone(destination) if destination else "",
                       is_reverification=bool(target),
                       error_message=COPY[error][language == "en"] if error else "")
    return render(request, "patients/guest_consultation.html", context, status=status)


def _detail(request, consultation, language):
    if request.method != "GET":
        raise Http404
    attachments = list(consultation.attachments.all())
    for attachment in attachments:
        attachment.access_url = localized_url("guest_consultation_attachment", language, public_id=attachment.public_id)
    audio = getattr(consultation, "audio_reply", None)
    submitted = request.session.pop("guest_consultation_submitted", None) == str(consultation.public_id)
    return render(request, "patients/guest_consultation.html", _context(
        request, language, consultation, state="detail", consultation=consultation,
        attachments=attachments, status_label=_consultation_status_label(consultation.status, language),
        submitted=submitted,
        audio_url=localized_url("guest_consultation_audio", language, public_id=audio.public_id) if audio else "",
    ))


@private_guest_response
@require_GET
def guest_media(request, public_id, language="ar", audio=False):
    model = TransientConsultationAudioReply if audio else TransientConsultationAttachment
    media = get_object_or_404(model.objects.select_related("consultation"), public_id=public_id)
    if not access.active_grant(request, media.consultation):
        raise Http404
    return _consultation_attachment_response(media)
