"""Root URLs extended with the production WhatsApp provider callback."""

from django.urls import include, path

from config.urls import handler404, urlpatterns as clinic_urlpatterns


urlpatterns = [
    path("integrations/whatsapp/", include("apps.whatsapp.urls")),
    *clinic_urlpatterns,
]
