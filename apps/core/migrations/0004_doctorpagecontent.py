# Generated for the owner-approved production closeout batch.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("clinic", "0002_doctorscheduleoverride"),
        ("core", "0003_patient_owned_reviews"),
    ]

    operations = [
        migrations.CreateModel(
            name="DoctorPageContent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hero_summary_ar", models.TextField(blank=True)),
                ("hero_summary_en", models.TextField(blank=True)),
                ("professional_bio_ar", models.TextField(blank=True)),
                ("professional_bio_en", models.TextField(blank=True)),
                ("experience_ar", models.TextField(blank=True, help_text="One item per line.")),
                ("experience_en", models.TextField(blank=True, help_text="One item per line.")),
                ("education_ar", models.TextField(blank=True, help_text="One item per line.")),
                ("education_en", models.TextField(blank=True, help_text="One item per line.")),
                ("boards_ar", models.TextField(blank=True, help_text="One item per line.")),
                ("boards_en", models.TextField(blank=True, help_text="One item per line.")),
                ("memberships_ar", models.TextField(blank=True, help_text="One item per line. Use: Label | ACRONYM")),
                ("memberships_en", models.TextField(blank=True, help_text="One item per line. Use: Label | ACRONYM")),
                ("awards_ar", models.TextField(blank=True, help_text="One item per line.")),
                ("awards_en", models.TextField(blank=True, help_text="One item per line.")),
                ("languages_ar", models.TextField(blank=True, help_text="One item per line.")),
                ("languages_en", models.TextField(blank=True, help_text="One item per line.")),
                ("specialties_ar", models.TextField(blank=True, help_text="One item per line.")),
                ("specialties_en", models.TextField(blank=True, help_text="One item per line.")),
                ("conditions_ar", models.TextField(blank=True, help_text="One item per line.")),
                ("conditions_en", models.TextField(blank=True, help_text="One item per line.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "doctor",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="page_content",
                        to="clinic.doctor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Doctor public page content",
                "verbose_name_plural": "Doctor public page content",
            },
        ),
    ]
