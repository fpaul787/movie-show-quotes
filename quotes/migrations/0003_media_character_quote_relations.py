import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Schema step 1: add new tables/columns alongside the legacy flat fields."""

    dependencies = [
        ("quotes", "0002_apikey"),
    ]

    operations = [
        migrations.CreateModel(
            name="Media",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("media_type", models.CharField(choices=[("MOVIE", "Movie"), ("TV_SHOW", "TV Show")], max_length=10)),
                ("release_year", models.PositiveSmallIntegerField()),
                ("external_id", models.CharField(blank=True, max_length=100, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name_plural": "media"},
        ),
        migrations.CreateModel(
            name="Character",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("media", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="characters", to="quotes.media")),
            ],
        ),
        migrations.AddIndex(
            model_name="media",
            index=models.Index(fields=["title"], name="quotes_medi_title_e78ee6_idx"),
        ),
        migrations.AddIndex(
            model_name="media",
            index=models.Index(fields=["media_type", "release_year"], name="quotes_medi_media_t_2840d9_idx"),
        ),
        migrations.AddConstraint(
            model_name="media",
            constraint=models.UniqueConstraint(
                condition=models.Q(("external_id__isnull", False)),
                fields=("external_id",),
                name="unique_media_external_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="media",
            constraint=models.UniqueConstraint(
                fields=("title", "media_type", "release_year"),
                name="unique_media_title_type_year",
            ),
        ),
        migrations.AddIndex(
            model_name="character",
            index=models.Index(fields=["name"], name="quotes_char_name_85e350_idx"),
        ),
        migrations.AddConstraint(
            model_name="character",
            constraint=models.UniqueConstraint(
                fields=("media", "name"), name="unique_character_name_per_media"
            ),
        ),
        # Legacy columns are kept (renamed where names collide) until data is migrated.
        migrations.RenameField("quote", "character", "legacy_character"),
        migrations.RenameField("quote", "created_at", "original_date"),
        migrations.AlterField(
            model_name="quote",
            name="original_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="quote",
            name="media",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name="quotes", to="quotes.media"),
        ),
        migrations.AddField(
            model_name="quote",
            name="character",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="quotes", to="quotes.character"),
        ),
        migrations.AddField(
            model_name="quote",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="quote",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
