from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reviewer_name", models.CharField(max_length=160)),
                ("body", models.TextField()),
                (
                    "rating",
                    models.PositiveSmallIntegerField(
                        validators=[MinValueValidator(1), MaxValueValidator(5)]
                    ),
                ),
                (
                    "language",
                    models.CharField(
                        choices=[("ar", "Arabic"), ("en", "English")],
                        db_index=True,
                        max_length=2,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[("google", "Google"), ("other", "Other approved source")],
                        default="google",
                        max_length=20,
                    ),
                ),
                (
                    "source_reference",
                    models.CharField(
                        blank=True,
                        help_text="Optional public source reference only. Do not store secrets or private URLs.",
                        max_length=255,
                    ),
                ),
                ("is_approved_for_publication", models.BooleanField(db_index=True, default=False)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("is_featured", models.BooleanField(db_index=True, default=False)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("reviewed_at", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["display_order", "-reviewed_at", "id"],
            },
        ),
    ]
