from django.db import migrations

SOURCE_TO_MEDIA_TYPE = {"movie": "MOVIE", "tv show": "TV_SHOW", "tv": "TV_SHOW"}
LANGUAGE_NAME_TO_CODE = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "zh",
    "russian": "ru",
    "hindi": "hi",
}


def _language_code(value):
    cleaned = value.strip()
    code = LANGUAGE_NAME_TO_CODE.get(cleaned.lower())
    if code:
        return code
    if len(cleaned) in (2, 3) and cleaned.isalpha():
        return cleaned.lower()
    raise ValueError(f"Cannot map legacy language {value!r} to an ISO code")


def forwards(apps, schema_editor):
    Quote = apps.get_model("quotes", "Quote")
    Media = apps.get_model("quotes", "Media")
    Character = apps.get_model("quotes", "Character")

    # Validate every row first so we abort rather than partially or lossily migrate.
    for quote in Quote.objects.all().iterator():
        if quote.source.strip().lower() not in SOURCE_TO_MEDIA_TYPE:
            raise ValueError(
                f"Quote {quote.pk}: cannot map source {quote.source!r} to a media type"
            )
        _language_code(quote.language)

    media_cache = {}
    character_cache = {}
    for quote in Quote.objects.all().iterator():
        media_type = SOURCE_TO_MEDIA_TYPE[quote.source.strip().lower()]
        title = quote.title.strip()
        media_key = (title.lower(), media_type, quote.year)
        media = media_cache.get(media_key)
        if media is None:
            media = Media.objects.filter(
                title__iexact=title, media_type=media_type, release_year=quote.year
            ).first() or Media.objects.create(
                title=title, media_type=media_type, release_year=quote.year
            )
            media_cache[media_key] = media

        character = None
        name = quote.legacy_character.strip()
        if name:
            character_key = (media.pk, name.lower())
            character = character_cache.get(character_key)
            if character is None:
                character = Character.objects.filter(
                    media=media, name__iexact=name
                ).first() or Character.objects.create(media=media, name=name)
                character_cache[character_key] = character

        Quote.objects.filter(pk=quote.pk).update(
            media=media, character=character, language=_language_code(quote.language)
        )


def backwards(apps, schema_editor):
    Quote = apps.get_model("quotes", "Quote")
    for quote in Quote.objects.select_related("media", "character").iterator():
        Quote.objects.filter(pk=quote.pk).update(
            title=quote.media.title,
            year=quote.media.release_year,
            source="Movie" if quote.media.media_type == "MOVIE" else "TV Show",
            legacy_character=quote.character.name if quote.character else "",
        )


class Migration(migrations.Migration):
    """Data step: build Media/Character rows from the legacy flat quote fields."""

    dependencies = [
        ("quotes", "0003_media_character_quote_relations"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
