"""Root URL configuration for Dr. Khaled Badran Clinic."""

from django.contrib import admin
from django.urls import path

from apps.core.views import health_check


urlpatterns = [
    path("", health_check, name="home"),
    path("health/", health_check, name="health"),
    path("admin/", admin.site.urls),
]
