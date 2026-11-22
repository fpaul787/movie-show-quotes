from django.db import migrations


def normalize_tags(apps, schema_editor):
    Quote = apps.get_model("quotes", "Quote")
    for quote in Quote.objects.only("id", "tags").iterator():
        if not isinstance(quote.tags, list) or not all(
            isinstance(t, str) for t in quote.tags
        ):
            continue
        normalized = list(dict.fromkeys(t.strip().lower() for t in quote.tags))
        if normalized != quote.tags:
            Quote.objects.filter(pk=quote.pk).update(tags=normalized)


class Migration(migrations.Migration):

    dependencies = [
        ("quotes", "0007_rate_limiting"),
    ]

    operations = [
        migrations.RunPython(normalize_tags, migrations.RunPython.noop),
    ]
