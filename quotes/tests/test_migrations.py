from importlib import import_module

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from ..models import Quote


class LegacyLanguageConversionTests(TestCase):
    def test_valid_language_codes_and_names(self):
        convert = import_module(
            "quotes.migrations.0004_populate_media_and_characters"
        )._language_code
        for value, expected in (
            ("English", "en"),
            (" EN ", "en"),
            ("pt-BR", "pt-BR"),
            ("PT-BR", "pt-BR"),
            ("en-abcdefgh-1234", "en-abcdefgh-1234"),
        ):
            with self.subTest(value=value):
                result = convert(value)
                self.assertEqual(result, expected)
                Quote._meta.get_field("language").clean(result, None)

    def test_invalid_language_codes_are_rejected(self):
        convert = import_module(
            "quotes.migrations.0004_populate_media_and_characters"
        )._language_code
        for value in (
            "\u65e5\u672c\u8a9e", "\u212aK", "en-abcdefgh-12345",
            "en-x", "en-123456789", "en--US",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert(value)


class TagNormalizationMigrationTests(TransactionTestCase):
    before = [("quotes", "0007_rate_limiting")]
    after = [("quotes", "0008_normalize_quote_tags")]

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def test_tags_are_normalized_without_losing_data(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        apps = executor.loader.project_state(self.before).apps
        Media_, Quote_ = apps.get_model("quotes", "Media"), apps.get_model("quotes", "Quote")
        media = Media_.objects.create(title="Dune", media_type="MOVIE", release_year=2021)
        make = lambda text, tags: Quote_.objects.create(  # noqa: E731
            text=text, media=media, language="en", tags=tags
        )
        make("a", [" Classic ", "classic", "Sci-Fi", "CLASSIC"])
        make("b", ["already", "fine"])
        make("c", [])

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)
        apps = executor.loader.project_state(self.after).apps
        Quote_ = apps.get_model("quotes", "Quote")
        self.assertEqual(Quote_.objects.get(text="a").tags, ["classic", "sci-fi"])
        self.assertEqual(Quote_.objects.get(text="b").tags, ["already", "fine"])
        self.assertEqual(Quote_.objects.get(text="c").tags, [])

        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        apps = executor.loader.project_state(self.before).apps
        self.assertEqual(apps.get_model("quotes", "Quote").objects.count(), 3)


class LegacyDataMigrationTests(TransactionTestCase):
    migrate_from = [("quotes", "0003_media_character_quote_relations")]
    migrate_to = [("quotes", "0005_remove_legacy_quote_fields")]

    def tearDown(self):
        call_command("migrate", verbosity=0)

    def _legacy_quote(self, apps, **overrides):
        data = dict(
            text="t", year=2021, title="Dune", character="Paul", source="Movie",
            language="English", tags=["a"], created_at="2021-10-22",
        )
        data.update(overrides)
        return apps.get_model("quotes", "Quote").objects.create(**data)

    def _go_to_legacy(self):
        executor = MigrationExecutor(connection)
        executor.migrate([("quotes", "0002_apikey")])
        return executor.loader.project_state([("quotes", "0002_apikey")]).apps

    def _migrate_forward(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        return executor.loader.project_state(self.migrate_to).apps

    def test_data_is_preserved_and_deduplicated(self):
        apps = self._go_to_legacy()
        self._legacy_quote(apps, text="one")
        self._legacy_quote(apps, text="two", title="dune", character="paul")
        self._legacy_quote(apps, text="three", character="")
        self._legacy_quote(apps, text="four", title="Fargo", source="TV Show", year=2014, character="Lester")

        apps = self._migrate_forward()
        Quote_, Media_, Character_ = (apps.get_model("quotes", n) for n in ("Quote", "Media", "Character"))

        self.assertEqual(Media_.objects.count(), 2)
        self.assertEqual(Character_.objects.count(), 2)
        one, two, three, four = (Quote_.objects.get(text=t) for t in ("one", "two", "three", "four"))
        self.assertEqual(one.media_id, two.media_id)
        self.assertEqual(one.character_id, two.character_id)
        self.assertIsNone(three.character_id)
        self.assertEqual(four.media.media_type, "TV_SHOW")
        self.assertEqual(one.language, "en")
        self.assertEqual(one.tags, ["a"])
        self.assertEqual(str(one.original_date), "2021-10-22")

    def test_language_codes_migrate_and_invalid_values_abort_before_writes(self):
        apps = self._go_to_legacy()
        self._legacy_quote(apps, text="valid", language="pt-BR")
        self._legacy_quote(apps, text="invalid", language="\u65e5\u672c\u8a9e")

        with self.assertRaisesRegex(ValueError, "Cannot map legacy language"):
            self._migrate_forward()

        apps = MigrationExecutor(connection).loader.project_state(self.migrate_from).apps
        Quote_ = apps.get_model("quotes", "Quote")
        self.assertIsNone(Quote_.objects.get(text="valid").media_id)
        self.assertEqual(Quote_.objects.get(text="valid").language, "pt-BR")
        Quote_.objects.filter(text="invalid").delete()

        apps = self._migrate_forward()
        quote = apps.get_model("quotes", "Quote").objects.get(text="valid")
        self.assertEqual(quote.language, "pt-BR")
        Quote._meta.get_field("language").clean(quote.language, None)

    def test_unmappable_legacy_values_abort_migration(self):
        apps = self._go_to_legacy()
        self._legacy_quote(apps, source="Podcast")
        with self.assertRaises(ValueError):
            self._migrate_forward()
        apps = MigrationExecutor(connection).loader.project_state([("quotes", "0003_media_character_quote_relations")]).apps
        Quote_ = apps.get_model("quotes", "Quote")
        self.assertEqual(Quote_.objects.count(), 1)
        Quote_.objects.all().delete()
