from django.http import HttpResponse


def health_check(request):
    return HttpResponse(
        "Dr. Khaled Badran Clinic foundation is running.",
        content_type="text/plain; charset=utf-8",
    )
