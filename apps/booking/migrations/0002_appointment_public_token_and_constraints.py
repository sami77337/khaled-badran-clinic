import uuid

from django.db import migrations, models


def populate_public_tokens(apps, schema_editor):
    Appointment = apps.get_model("booking", "Appointment")
    for appointment in Appointment.objects.filter(public_token__isnull=True):
        appointment.public_token = uuid.uuid4()
        appointment.save(update_fields=["public_token"])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="public_token",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                null=True,
            ),
        ),
        migrations.RunPython(populate_public_tokens, reverse_noop),
        migrations.AlterField(
            model_name="appointment",
            name="public_token",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="appointment",
            constraint=models.UniqueConstraint(
                fields=("doctor", "starts_at", "status"),
                name="unique_appointment_doctor_start_status",
            ),
        ),
    ]
