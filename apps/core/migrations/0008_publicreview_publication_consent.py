from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_doctorpagecontent_profile_photo")]

    operations = [
        migrations.AddField(
            model_name="publicreview",
            name="publication_consent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="publicreview",
            name="publication_consent_version",
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AddField(
            model_name="publicreview",
            name="publication_consent_language",
            field=models.CharField(blank=True, max_length=2),
        ),
        migrations.AddField(
            model_name="publicreview",
            name="publication_withdrawn_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
