from django.conf import settings
from django.db import models


class StaffPushSubscription(models.Model):
    """Private delivery credentials. Deliberately not exposed in Django admin."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    endpoint = models.CharField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=87)
    auth = models.CharField(max_length=22)
    language = models.CharField(max_length=2, choices=[("ar", "Arabic"), ("en", "English")])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
