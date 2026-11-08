from datetime import timedelta
from importlib import import_module

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import APIKey, Character, Media, Quote


class HomepageTests(TestCase):
    def test_root_serves_react_homepage(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, '<div id="root" data-username=""></div>', html=False
        )

    def test_root_includes_logged_in_username(self):
        user = get_user_model().objects.create_user(
            username="homepage-user", password="a-Long-unusual-pass-123"
        )
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-username="homepage-user"')

    def test_legacy_homepage_url_redirects_to_root(self):
        response = self.client.get("/homepage/")

        self.assertRedirects(
            response, "/", status_code=301, fetch_redirect_response=False
        )

    def test_signup_page_serves_the_react_app(self):
        response = self.client.get("/signup/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"')

    def test_login_page_serves_the_react_app(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"')

    def test_profile_api_keys_page_serves_the_react_app(self):
        response = self.client.get("/profile/api-keys/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"')


class APIKeyTests(TestCase):
    def setUp(self):
        self.apikey = APIKey(name="test")
        self.raw_key = self.apikey.set_new_key()
        self.apikey.save()

    def test_missing_or_wrong_key_returns_401(self):
        self.assertEqual(self.client.get("/quotes/random").status_code, 401)
        response = self.client.get(
            "/quotes/random", headers={"Authorization": "Api-Key wrong.key"}
        )
        self.assertEqual(response.status_code, 401)

    def test_raw_key_is_not_stored(self):
        self.assertNotIn(self.raw_key, self.apikey.hashed_key)
        self.assertNotEqual(self.raw_key, self.apikey.hashed_key)

    def test_valid_key_works_via_either_header_and_records_usage(self):
        for headers in (
            {"Authorization": f"Api-Key {self.raw_key}"},
            {"X-API-Key": self.raw_key},
            {"X-API-Key": f"  {self.raw_key}  "},
        ):
            self.assertEqual(
                self.client.get("/quotes/random", headers=headers).status_code, 404
            )
        self.apikey.refresh_from_db()
        self.assertIsNotNone(self.apikey.last_used_at)

    def test_revoked_or_expired_key_returns_403(self):
        headers = {"X-API-Key": self.raw_key}
        self.apikey.is_active = False
        self.apikey.save()
        self.assertEqual(self.client.get("/quotes/random", headers=headers).status_code, 403)

        self.apikey.is_active = True
        self.apikey.expires_at = timezone.now() - timedelta(days=1)
        self.apikey.save()
        self.assertEqual(self.client.get("/quotes/random", headers=headers).status_code, 403)


class UserAPIKeyEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="keyuser", password="pw-12345-xyz"
        )

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/keys").status_code, 401)
        self.assertEqual(self.client.post("/api/keys").status_code, 401)
        self.assertEqual(self.client.delete("/api/keys").status_code, 401)

    def test_create_and_delete_require_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        self.assertEqual(client.post("/api/keys").status_code, 403)
        self.assertFalse(APIKey.objects.filter(owner=self.user).exists())

        token = client.get("/api/auth/csrf").json()["csrfToken"]
        self.assertEqual(
            client.post("/api/keys", headers={"X-CSRFToken": token}).status_code,
            201,
        )
        self.assertTrue(APIKey.objects.filter(owner=self.user).exists())

        self.assertEqual(client.delete("/api/keys").status_code, 403)
        self.assertTrue(APIKey.objects.filter(owner=self.user).exists())
        self.assertEqual(
            client.delete("/api/keys", headers={"X-CSRFToken": token}).status_code,
            200,
        )
        self.assertFalse(APIKey.objects.filter(owner=self.user).exists())

    def test_no_key_initially(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/keys").json(), {"api_key": None})

    def test_create_key_shows_it_once_and_it_works(self):
        self.client.force_login(self.user)
        created = self.client.post("/api/keys")
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()["api_key"]["is_active"])
        raw = created.json()["api_key"]["key"]
        self.assertEqual(APIKey.objects.get(owner=self.user).hashed_key, APIKey._hash(raw))

        listed = self.client.get("/api/keys").json()["api_key"]
        self.assertNotIn("key", listed)
        self.assertTrue(listed["is_active"])
        self.assertEqual(listed["prefix"], raw.split(".")[0])
        self.client.logout()
        response = self.client.get("/quotes/random", headers={"X-API-Key": raw})
        self.assertEqual(response.status_code, 404)

    def test_key_status_matches_usability(self):
        self.client.force_login(self.user)
        created = self.client.post("/api/keys")
        raw_key = created.json()["api_key"]["key"]
        key = APIKey.objects.get(owner=self.user)
        now = timezone.now()

        for is_active, expires_at, expected_status, expected_quote_status in (
            (True, None, True, 404),
            (True, now + timedelta(days=1), True, 404),
            (True, now - timedelta(days=1), False, 403),
            (False, None, False, 403),
            (False, now + timedelta(days=1), False, 403),
        ):
            with self.subTest(is_active=is_active, expires_at=expires_at):
                key.is_active = is_active
                key.expires_at = expires_at
                key.save(update_fields=["is_active", "expires_at"])

                response = self.client.get("/api/keys")
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json()["api_key"]["is_active"], expected_status)
                self.assertEqual(
                    self.client.get(
                        "/quotes/random", headers={"X-API-Key": raw_key}
                    ).status_code,
                    expected_quote_status,
                )

    def test_create_key_name_fits_for_long_usernames(self):
        self.client.force_login(self.user)
        for username_length in (95, 96, 97, 150):
            with self.subTest(username_length=username_length):
                self.user.username = "u" * username_length
                self.user.save(update_fields=["username"])

                response = self.client.post("/api/keys")

                self.assertEqual(response.status_code, 201)
                expected_name = "u" * min(username_length, 96) + " key"
                self.assertEqual(response.json()["api_key"]["name"], expected_name)
                self.assertEqual(APIKey.objects.get(owner=self.user).name, expected_name)
                APIKey.objects.filter(owner=self.user).delete()

    def test_second_key_is_rejected(self):
        self.client.force_login(self.user)
        self.client.post("/api/keys")
        self.assertEqual(self.client.post("/api/keys").status_code, 409)
        self.assertEqual(APIKey.objects.filter(owner=self.user).count(), 1)

    def test_delete_key_allows_creating_a_replacement(self):
        self.client.force_login(self.user)
        created = self.client.post("/api/keys")
        raw_key = created.json()["api_key"]["key"]

        deleted = self.client.delete("/api/keys")

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"deleted": True})
        self.assertFalse(APIKey.objects.filter(owner=self.user).exists())
        self.assertEqual(
            self.client.get("/quotes/random", headers={"X-API-Key": raw_key}).status_code,
            401,
        )
        self.assertEqual(self.client.post("/api/keys").status_code, 201)

    def test_cannot_delete_another_users_key(self):
        other = get_user_model().objects.create_user(
            username="other", password="test-password"
        )
        other_key = APIKey(name="other key", owner=other)
        other_key.set_new_key()
        other_key.save()
        self.client.force_login(self.user)

        response = self.client.delete("/api/keys")

        self.assertEqual(response.status_code, 404)
        self.assertTrue(APIKey.objects.filter(pk=other_key.pk).exists())

    def test_keys_are_per_user(self):
        other = get_user_model().objects.create_user(username="other", password="pw-12345-xyz")
        self.client.force_login(other)
        self.client.post("/api/keys")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/api/keys").json(), {"api_key": None})


class QuoteEndpointTests(TestCase):
    def setUp(self):
        key = APIKey(name="test")
        raw_key = key.set_new_key()
        key.save()
        self.client.defaults["HTTP_X_API_KEY"] = raw_key
    def test_quote_returns_a_quote_from_the_database_as_json(self):
        media = Media.objects.create(
            title="Star Wars", media_type="MOVIE", release_year=1977
        )
        han = Character.objects.create(name="Han Solo", media=media)
        Quote.objects.create(
            text="May the Force be with you.",
            media=media,
            character=han,
            language="en",
            tags=["classic", "sci-fi"],
            original_date="1977-05-25",
        )

        response = self.client.get("/quotes/random")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "text": "May the Force be with you.",
                "year": 1977,
                "title": "Star Wars",
                "character": "Han Solo",
                "source": "Movie",
                "language": "en",
                "tags": ["classic", "sci-fi"],
                "created_at": "1977-05-25",
            },
        )

    def test_quote_without_character_returns_empty_character(self):
        media = Media.objects.create(
            title="Star Wars", media_type="MOVIE", release_year=1977
        )
        Quote.objects.create(text="Hi", media=media, language="en")

        data = self.client.get("/quotes/random").json()

        self.assertEqual(data["character"], "")
        self.assertIsNone(data["created_at"])

    def test_quote_returns_one_of_the_stored_quotes(self):
        for i in range(5):
            media = Media.objects.create(
                title=f"Title {i}", media_type="MOVIE", release_year=2000 + i
            )
            Quote.objects.create(
                text=f"Quote {i}",
                media=media,
                character=Character.objects.create(name="Someone", media=media),
                language="en",
            )

        texts = {f"Quote {i}" for i in range(5)}
        for _ in range(10):
            self.assertIn(self.client.get("/quotes/random").json()["text"], texts)

    def test_quote_does_not_create_quotes(self):
        self.client.get("/quotes/random")

        self.assertEqual(Quote.objects.count(), 0)

    def test_quote_returns_404_when_no_quotes_exist(self):
        response = self.client.get("/quotes/random")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "No quotes available"})


class QuoteFixtureTests(TestCase):
    def test_fixture_loads_with_timestamps_and_relationships(self):
        call_command("loaddata", "quotes", verbosity=0)

        for model in (Media, Character, Quote):
            with self.subTest(model=model.__name__):
                self.assertEqual(model.objects.count(), 15)
                self.assertFalse(
                    model.objects.filter(created_at__isnull=True).exists()
                )
                self.assertFalse(
                    model.objects.filter(updated_at__isnull=True).exists()
                )

        for quote in Quote.objects.select_related("character"):
            self.assertEqual(quote.media_id, quote.character.media_id)


class CharacterAdminTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser(
            username="admin", password="test-password"
        )
        self.client.force_login(admin)
        self.media = Media.objects.create(
            title="Original", media_type="MOVIE", release_year=2000
        )
        self.other = Media.objects.create(
            title="Other", media_type="MOVIE", release_year=2001
        )
        self.character = Character.objects.create(name="Speaker", media=self.media)
        self.url = reverse("admin:quotes_character_change", args=[self.character.pk])

    def test_media_is_read_only_when_character_has_quotes(self):
        quote = Quote.objects.create(
            text="Hello", media=self.media, character=self.character, language="en"
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, 'name="media"')

        response = self.client.post(
            self.url, {"name": "Renamed", "media": self.other.pk, "_save": "Save"}
        )
        self.assertEqual(response.status_code, 302)
        self.character.refresh_from_db()
        quote.refresh_from_db()
        self.assertEqual(self.character.name, "Renamed")
        self.assertEqual(self.character.media_id, self.media.pk)
        self.assertEqual(quote.media_id, self.character.media_id)

    def test_media_can_be_changed_without_quotes(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="media"')

        response = self.client.post(
            self.url, {"name": "Speaker", "media": self.other.pk, "_save": "Save"}
        )
        self.assertEqual(response.status_code, 302)
        self.character.refresh_from_db()
        self.assertEqual(self.character.media_id, self.other.pk)

    def test_media_is_editable_when_adding_character(self):
        response = self.client.get(reverse("admin:quotes_character_add"))
        self.assertContains(response, 'name="media"')


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
        quote = Quote(text="x", media=self.media, character=paul, language="en")
        with self.assertRaises(ValidationError):
            quote.full_clean()

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
