from pathlib import PurePosixPath

from django.http import FileResponse, Http404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.clinic.models import Doctor

from .models import DoctorPageContent


@require_GET
@never_cache
def doctor_photo(request):
    doctor = Doctor.objects.filter(is_active=True).order_by("display_order", "id").first()
    if doctor is None:
        raise Http404("Doctor photo unavailable.")

    content = DoctorPageContent.objects.filter(doctor=doctor).only(
        "profile_photo", "profile_photo_content_type"
    ).first()
    if content is None or not content.profile_photo or not content.profile_photo.name:
        raise Http404("Doctor photo unavailable.")

    suffix = PurePosixPath(content.profile_photo.name).suffix.lower()
    filename = f"doctor-photo{suffix}" if suffix else "doctor-photo"
    try:
        response = FileResponse(
            content.profile_photo.open("rb"),
            as_attachment=False,
            filename=filename,
            content_type=content.profile_photo_content_type or "application/octet-stream",
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise Http404("Doctor photo unavailable.") from exc

    response["X-Content-Type-Options"] = "nosniff"
    return response
