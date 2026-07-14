from django.urls import path

from . import views


urlpatterns = [
    path(
        "private-media/<uuid:public_id>/download/",
        views.private_media_download,
        name="record_private_media_download",
    ),
]
