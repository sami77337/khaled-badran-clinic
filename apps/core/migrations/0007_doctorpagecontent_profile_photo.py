import apps.core.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_publicsitecontent_doctorpagesection"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorpagecontent",
            name="profile_photo",
            field=models.FileField(
                blank=True,
                storage=apps.core.storage.PublicSiteMediaStorage(),
                upload_to=apps.core.storage.doctor_photo_upload_path,
            ),
        ),
        migrations.AddField(
            model_name="doctorpagecontent",
            name="profile_photo_content_type",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
