"""Guard Django Admin login without changing its built-in authentication."""

from django.contrib import admin
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters

from apps.patients import rate_limits


ADMIN_THROTTLE_NOTICE = (
    "محاولات تسجيل دخول كثيرة. يرجى المحاولة لاحقًا. / "
    "Too many login attempts. Please try again later."
)


@sensitive_post_parameters("password")
@csrf_protect
@never_cache
def throttled_admin_login(request):
    """Throttle Admin POSTs before delegating to Django's normal login view."""
    if request.method == "POST" and not admin.site.has_permission(request):
        result = rate_limits.check_admin_login_attempt_rate_limit(
            request, username=request.POST.get("username", ""),
        )
        if not result.allowed:
            return HttpResponse(
                ADMIN_THROTTLE_NOTICE,
                status=429,
                content_type="text/plain; charset=utf-8",
            )
    return admin.site.login(request)
