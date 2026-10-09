from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("booking", "0008_editable_message_defaults")]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="booking_whatsapp_consent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="appointment",
            name="booking_whatsapp_consent_version",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="appointment",
            name="booking_whatsapp_consent_language",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="appointment",
            name="booking_whatsapp_consent_withdrawn_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
