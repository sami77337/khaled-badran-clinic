from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0010_clinic_doctor_staff_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultation",
            name="whatsapp_reply_consent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="consultation",
            name="whatsapp_reply_consent_language",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="consultation",
            name="whatsapp_reply_consent_version",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="consultation",
            name="whatsapp_reply_consent_withdrawn_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transientconsultation",
            name="whatsapp_reply_consent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transientconsultation",
            name="whatsapp_reply_consent_language",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="transientconsultation",
            name="whatsapp_reply_consent_version",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="transientconsultation",
            name="whatsapp_reply_consent_withdrawn_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
