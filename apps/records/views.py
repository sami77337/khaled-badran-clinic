from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import RecordMedia


def _staff_required(view_func):
    @wraps(view_func)
    @never_cache
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.get_full_path(),
                login_url=f"{reverse('login')}?role=doctor",
            )
        if not request.user.is_staff:
            return HttpResponseForbidden("Staff access required.")
        return view_func(request, *args, **kwargs)

    return wrapped


@require_GET
@_staff_required
def private_media_download(request, public_id):
    media = get_object_or_404(
        RecordMedia.objects.select_related("patient", "visit"),
        public_id=public_id,
        is_active=True,
        trashed_at__isnull=True,
    )
    if not media.file:
        raise Http404("Private media file is unavailable.")
    if not media.file.storage.exists(media.file.name):
        raise Http404("Private media file is unavailable.")

    response = FileResponse(
        media.file.open("rb"),
        as_attachment=True,
        filename=media.download_filename,
        content_type=media.content_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
@_staff_required
def private_media_view(request, public_id):
    media = get_object_or_404(
        RecordMedia.objects.select_related("patient", "visit"),
        public_id=public_id,
        is_active=True,
        trashed_at__isnull=True,
    )
    if not media.file:
        raise Http404("Private media file is unavailable.")
    if not media.file.storage.exists(media.file.name):
        raise Http404("Private media file is unavailable.")

    response = FileResponse(
        media.file.open("rb"),
        as_attachment=False,
        filename=media.presentation_filename,
        content_type=media.content_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
