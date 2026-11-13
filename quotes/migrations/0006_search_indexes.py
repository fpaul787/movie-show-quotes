from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Trigram and JSON indexes for quote search and filtering."""

    dependencies = [
        ("quotes", "0005_remove_legacy_quote_fields"),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name="quote",
            index=GinIndex(fields=["tags"], name="quote_tags_gin_idx"),
        ),
        migrations.AddIndex(
            model_name="quote",
            index=GinIndex(
                fields=["text"], name="quote_text_trgm_idx", opclasses=["gin_trgm_ops"]
            ),
        ),
        migrations.AddIndex(
            model_name="media",
            index=GinIndex(
                fields=["title"], name="media_title_trgm_idx", opclasses=["gin_trgm_ops"]
            ),
        ),
        migrations.AddIndex(
            model_name="character",
            index=GinIndex(
                fields=["name"], name="character_name_trgm_idx", opclasses=["gin_trgm_ops"]
            ),
        ),
    ]
