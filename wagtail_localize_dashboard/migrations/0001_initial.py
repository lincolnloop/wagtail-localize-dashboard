# Initial migration for wagtail-localize-dashboard

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("wagtailcore", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TranslationProgress",
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
                    "percent_translated",
                    models.IntegerField(
                        default=0, help_text="Percentage of segments translated (0-100)"
                    ),
                ),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source_page",
                    models.ForeignKey(
                        db_index=True,
                        help_text="The original source page",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translation_progress_source",
                        to="wagtailcore.page",
                    ),
                ),
                (
                    "translated_page",
                    models.ForeignKey(
                        db_index=True,
                        help_text="The translated page",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="translation_progress_translated",
                        to="wagtailcore.page",
                    ),
                ),
            ],
            options={
                "verbose_name": "Translation Progress",
                "verbose_name_plural": "Translation Progress",
                "ordering": ["-last_updated"],
                "unique_together": {("source_page", "translated_page")},
                "indexes": [
                    models.Index(
                        fields=["percent_translated"], name="trans_prog_percent_idx"
                    ),
                    models.Index(
                        fields=["last_updated"], name="trans_prog_updated_idx"
                    ),
                ],
            },
        ),
    ]
