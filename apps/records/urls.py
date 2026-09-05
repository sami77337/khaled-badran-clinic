from django.urls import path

from . import views


urlpatterns = [
    path(
        "patients/<int:patient_id>/private-media/<uuid:public_id>/view/",
        views.private_media_view,
        name="record_private_media_view",
    ),
    path(
        "patients/<int:patient_id>/private-media/<uuid:public_id>/download/",
        views.private_media_download,
        name="record_private_media_download",
    ),
]
