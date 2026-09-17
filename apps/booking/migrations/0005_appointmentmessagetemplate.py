import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.booking.message_template_validation


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0004_appointment_contact_phone_e164_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AppointmentMessageTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event",
                    models.CharField(
                        choices=[("arrived", "Arrived"), ("no_show", "No-show")],
                        max_length=20,
                        unique=True,
                    ),
                ),
                ("is_active", models.BooleanField(default=False)),
                (
                    "text_ar",
                    models.TextField(
                        blank=True,
                        max_length=2000,
                        validators=[
                            apps.booking.message_template_validation.validate_appointment_message_template
                        ],
                    ),
                ),
                (
                    "text_en",
                    models.TextField(
                        blank=True,
                        max_length=2000,
                        validators=[
                            apps.booking.message_template_validation.validate_appointment_message_template
                        ],
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="appointment_message_template_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["event"]},
        ),
    ]
