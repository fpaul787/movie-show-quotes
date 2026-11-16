from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db.models import F
from django.test import TestCase

from ..models import Character, Media, Quote


class SeedQuotesTests(TestCase):
    def test_seed_loads_fixture_and_skips_on_repeat(self):
        call_command("seed_quotes", stdout=StringIO())
        self.assertTrue(Media.objects.exists())
        self.assertTrue(Character.objects.exists())
        self.assertTrue(Quote.objects.exists())
        quote = Quote.objects.select_related("media", "character").first()
        self.assertEqual(quote.character.media_id, quote.media_id)
        self.assertIsNotNone(quote.created_at)
        self.assertFalse(
            Quote.objects.exclude(character__media_id=F("media_id")).exists()
        )
        media = Media.objects.first()
        media.title = "Existing title"
        media.save()

        output = StringIO()
        call_command("seed_quotes", stdout=output)
        media.refresh_from_db()
        self.assertEqual(media.title, "Existing title")
        self.assertIn("Skipping quote seed", output.getvalue())

    def test_seed_skips_when_only_media_exists(self):
        Media.objects.create(title="Existing", media_type="MOVIE", release_year=2000)
        output = StringIO()
        call_command("seed_quotes", stdout=output)
        self.assertEqual(Media.objects.count(), 1)
        self.assertFalse(Character.objects.exists())
        self.assertFalse(Quote.objects.exists())
        self.assertIn("Skipping quote seed", output.getvalue())

    def test_seed_skips_when_quotes_exist(self):
        media = Media.objects.create(title="Existing", media_type="MOVIE", release_year=2000)
        Quote.objects.create(text="Existing", media=media, language="en")
        output = StringIO()
        call_command("seed_quotes", stdout=output)
        self.assertEqual(Quote.objects.count(), 1)
        self.assertFalse(Character.objects.exists())
        self.assertIn("Skipping quote seed", output.getvalue())

    def test_seed_rolls_back_if_fixture_load_fails(self):
        def fail_load(*args, **kwargs):
            Media.objects.create(title="Partial", media_type="MOVIE", release_year=2000)
            raise ValueError("fixture failed")

        with patch("quotes.management.commands.seed_quotes.call_command", side_effect=fail_load):
            with self.assertRaisesMessage(ValueError, "fixture failed"):
                call_command("seed_quotes", stdout=StringIO())
        self.assertFalse(Media.objects.exists())


class QuoteFixtureTests(TestCase):
    def test_fixture_loads_with_timestamps_and_relationships(self):
        call_command("loaddata", "quotes", verbosity=0)

        for model in (Media, Character, Quote):
            with self.subTest(model=model.__name__):
                self.assertTrue(model.objects.exists())
                self.assertFalse(
                    model.objects.filter(created_at__isnull=True).exists()
                )
                self.assertFalse(
                    model.objects.filter(updated_at__isnull=True).exists()
                )

        for quote in Quote.objects.select_related("character"):
            self.assertEqual(quote.media_id, quote.character.media_id)
