from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from ..models import Character, Media, Quote


class NormalizedModelTests(TestCase):
    def setUp(self):
        self.media = Media.objects.create(
            title="Dune", media_type="MOVIE", release_year=2021
        )
        self.other = Media.objects.create(
            title="Dune", media_type="MOVIE", release_year=1984
        )

    def test_media_type_is_normalized_on_save(self):
        media = Media.objects.create(title="Fargo", media_type="tv-show", release_year=2014)
        self.assertEqual(media.media_type, Media.MediaType.TV_SHOW)

    def test_tags_are_normalized_on_save(self):
        quote = Quote.objects.create(
            text="x", media=self.media, language="en",
            tags=[" Classic ", "SCI-FI", "classic", "Sci-Fi"],
        )
        quote.refresh_from_db()
        self.assertEqual(quote.tags, ["classic", "sci-fi"])

    def test_tags_are_normalized_on_clean(self):
        quote = Quote(text="x", media=self.media, language="en", tags=["A", "a", "B"])
        quote.clean()
        self.assertEqual(quote.tags, ["a", "b"])

    def test_fixture_tags_are_normalized(self):
        import json
        from pathlib import Path

        import quotes

        path = Path(quotes.__file__).parent / "fixtures" / "quotes.json"
        for entry in json.loads(path.read_text(encoding="utf-8")):
            tags = entry.get("fields", {}).get("tags")
            if isinstance(tags, list):
                self.assertEqual(tags, Quote.normalize_tags(tags), entry)

    def test_media_duplicate_title_type_year_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Media.objects.create(title="Dune", media_type="MOVIE", release_year=2021)

    def test_external_id_unique_when_set_but_optional(self):
        Media.objects.create(title="A", media_type="MOVIE", release_year=2000)
        Media.objects.create(title="B", media_type="MOVIE", release_year=2000)
        Media.objects.create(title="C", media_type="MOVIE", release_year=2000, external_id="tt1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Media.objects.create(title="D", media_type="MOVIE", release_year=2000, external_id="tt1")

    def test_character_unique_within_media_only(self):
        Character.objects.create(name="Paul", media=self.media)
        Character.objects.create(name="Paul", media=self.other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Character.objects.create(name="Paul", media=self.media)

    def test_quote_character_must_belong_to_same_media(self):
        paul = Character.objects.create(name="Paul", media=self.other)
        quote = Quote(
            text="x", media=self.media, character=paul, language="en", tags=["test"]
        )
        with self.assertRaises(ValidationError) as raised:
            quote.full_clean()
        self.assertEqual(
            raised.exception.message_dict,
            {"character": ["Character must belong to the quote's media."]},
        )

    def test_quote_validates_language_and_tags(self):
        for kwargs in ({"language": "English"}, {"language": "en", "tags": "nope"}, {"language": "en", "tags": [1]}):
            with self.assertRaises(ValidationError):
                Quote(text="x", media=self.media, **kwargs).full_clean()
        Quote(text="x", media=self.media, language="pt-BR", tags=["a"]).full_clean()

    def test_deleting_character_keeps_quote(self):
        paul = Character.objects.create(name="Paul", media=self.media)
        quote = Quote.objects.create(text="x", media=self.media, character=paul, language="en")
        paul.delete()
        quote.refresh_from_db()
        self.assertIsNone(quote.character)

    def test_deleting_media_cascades(self):
        Quote.objects.create(text="x", media=self.media, language="en")
        self.media.delete()
        self.assertEqual(Quote.objects.count(), 0)
