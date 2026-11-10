import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Schema step 2: drop legacy columns now that data lives in Media/Character."""

    dependencies = [
        ("quotes", "0004_populate_media_and_characters"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quote",
            name="media",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quotes", to="quotes.media"),
        ),
        migrations.AlterField(
            model_name="quote",
            name="language",
            field=models.CharField(
                max_length=16,
                validators=[
                    django.core.validators.RegexValidator(
                        "^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$",
                        "Enter a lowercase ISO 639 language code, e.g. 'en' or 'pt-BR'.",
                    )
                ],
            ),
        ),
        migrations.RemoveField(model_name="quote", name="title"),
        migrations.RemoveField(model_name="quote", name="year"),
        migrations.RemoveField(model_name="quote", name="source"),
        migrations.RemoveField(model_name="quote", name="legacy_character"),
        migrations.AddIndex(
            model_name="quote",
            index=models.Index(fields=["language"], name="quotes_quot_languag_e03037_idx"),
        ),
        migrations.AddIndex(
            model_name="quote",
            index=models.Index(fields=["media", "character"], name="quotes_quot_media_i_a6b290_idx"),
        ),
    ]
