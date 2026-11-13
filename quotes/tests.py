import re
import random
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
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

RANDOM_URL = "/api/v1/quotes/random/"
LIST_URL = "/api/v1/quotes/"
DETAIL_URL = "/api/v1/quotes/1/"
# Add each new data endpoint here so it is covered by the auth tests.
DATA_URLS = [RANDOM_URL, LIST_URL, DETAIL_URL]

class SeedQuotesTests(TestCase):
    def test_seed_loads_fixture_and_skips_on_repeat(self):
        call_command("seed_quotes", stdout=StringIO())
        self.assertEqual(Media.objects.count(), 15)
        self.assertEqual(Character.objects.count(), 15)
        self.assertEqual(Quote.objects.count(), 15)
        quote = Quote.objects.select_related("media", "character").get(pk=2)
        self.assertEqual(quote.character.media_id, quote.media_id)
        self.assertIsNotNone(quote.created_at)
        media = Media.objects.get(pk=1)
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
        response = self.client.get(RANDOM_URL)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "missing_api_key")
        response = self.client.get(
            RANDOM_URL, headers={"Authorization": "Api-Key wrong.key"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_api_key")

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
                self.client.get(RANDOM_URL, headers=headers).status_code, 404
            )
        self.apikey.refresh_from_db()
        self.assertIsNotNone(self.apikey.last_used_at)

    def test_revoked_or_expired_key_returns_403(self):
        headers = {"X-API-Key": self.raw_key}
        self.apikey.is_active = False
        self.apikey.save()
        for url in DATA_URLS:
            with self.subTest(url=url, state="revoked"):
                response = self.client.get(url, headers=headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"]["code"], "revoked_api_key")

        self.apikey.is_active = True
        self.apikey.expires_at = timezone.now() - timedelta(days=1)
        self.apikey.save()
        for url in DATA_URLS:
            with self.subTest(url=url, state="expired"):
                response = self.client.get(url, headers=headers)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"]["code"], "expired_api_key")

    def test_v1_endpoint_uses_the_same_authentication(self):
        url = reverse("api_v1:random-quote")
        self.assertEqual(url, "/api/v1/quotes/random/")
        self.assertEqual(self.client.get(url).status_code, 401)
        headers = {"X-API-Key": self.raw_key}
        self.assertEqual(self.client.get(url, headers=headers).status_code, 404)
        self.apikey.is_active = False
        self.apikey.save()
        self.assertEqual(self.client.get(url, headers=headers).status_code, 403)

    def test_unknown_v1_path_returns_json_404(self):
        response = self.client.get("/api/v1/nope/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "resource_not_found")

    def test_data_endpoints_are_read_only(self):
        headers = {"X-API-Key": self.raw_key}
        for url in DATA_URLS:
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url, headers=headers)
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(response.json()["error"]["code"], "method_not_allowed")
                    self.assertIn("GET", response["Allow"])

    def test_unauthenticated_write_requests_return_401(self):
        for url in DATA_URLS:
            self.assertEqual(self.client.post(url).status_code, 401)

    def test_all_data_endpoints_enforce_key_states(self):
        for url in DATA_URLS:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 401)
                self.assertEqual(
                    self.client.get(url, headers={"X-API-Key": "bad.key"}).status_code,
                    401,
                )

    def test_key_of_deactivated_owner_returns_403(self):
        user = get_user_model().objects.create_user("owner", "o@example.com", "pw")
        self.apikey.owner = user
        self.apikey.save()
        headers = {"X-API-Key": self.raw_key}
        self.assertEqual(self.client.get(RANDOM_URL, headers=headers).status_code, 404)
        user.is_active = False
        user.save()
        response = self.client.get(RANDOM_URL, headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "revoked_api_key")

    def test_save_retries_when_prefix_is_taken_at_insert_time(self):
        # The prefix looked free when generated but is taken at save time (race).
        with patch(
            "quotes.models.secrets.token_hex", side_effect=[self.apikey.prefix, "abcd1234"]
        ):
            key = APIKey(name="other")
            raw_key = key.save_with_new_key()
        self.assertEqual(key.prefix, "abcd1234")
        self.assertTrue(raw_key.startswith("abcd1234."))
        self.assertEqual(APIKey.objects.count(), 2)
        self.assertEqual(APIKey.authenticate(raw_key), key)


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
        response = self.client.get(RANDOM_URL, headers={"X-API-Key": raw})
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
                        RANDOM_URL, headers={"X-API-Key": raw_key}
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
            self.client.get(RANDOM_URL, headers={"X-API-Key": raw_key}).status_code,
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
        quote = Quote.objects.create(
            text="May the Force be with you.",
            media=media,
            character=han,
            language="en",
            tags=["classic", "sci-fi"],
            original_date="1977-05-25",
        )

        response = self.client.get(RANDOM_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": quote.id,
                "text": "May the Force be with you.",
                "language": "en",
                "tags": ["classic", "sci-fi"],
                "character": {"id": han.id, "name": "Han Solo"},
                "media": {
                    "id": media.id,
                    "title": "Star Wars",
                    "media_type": "MOVIE",
                    "release_year": 1977,
                },
            },
        )

    def test_quote_without_character_returns_null_character(self):
        media = Media.objects.create(
            title="Star Wars", media_type="MOVIE", release_year=1977
        )
        Quote.objects.create(text="Hi", media=media, language="en")

        data = self.client.get(RANDOM_URL).json()

        self.assertIsNone(data["character"])

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
            self.assertIn(self.client.get(RANDOM_URL).json()["text"], texts)

    def test_quote_does_not_create_quotes(self):
        self.client.get(RANDOM_URL)

        self.assertEqual(Quote.objects.count(), 0)

    def test_quote_returns_404_when_no_quotes_exist(self):
        response = self.client.get(RANDOM_URL)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"error": {"code": "no_quotes_available", "message": "No quotes available."}},
        )

    def test_legacy_random_quote_route_is_removed(self):
        self.assertEqual(self.client.get("/quotes/random").status_code, 404)


class ErrorAndPerformanceTests(TestCase):
    def setUp(self):
        key = APIKey(name="test")
        raw_key = key.set_new_key()
        key.save()
        self.client.defaults["HTTP_X_API_KEY"] = raw_key
        media = Media.objects.create(title="M", media_type="MOVIE", release_year=2000)
        for i in range(5):
            Quote.objects.create(
                text=f"Quote {i}",
                media=media,
                character=Character.objects.create(name=f"C{i}", media=media),
                language="en",
            )

    def test_random_quote_uses_constant_queries(self):
        # One auth lookup, one last_used update, count, and the quote itself.
        with self.assertNumQueries(4):
            self.assertEqual(self.client.get(RANDOM_URL).status_code, 200)

    def test_list_query_count_does_not_grow_with_results(self):
        with self.assertNumQueries(4):
            self.assertEqual(self.client.get(LIST_URL).status_code, 200)

    def test_filtered_list_query_count_is_constant(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                LIST_URL, {"search": "quote", "media": "M", "language": "en"}
            )
        self.assertEqual(response.status_code, 200)

    def test_random_quote_survives_deletion_between_count_and_fetch(self):
        real_randrange = random.randrange

        def delete_then_pick(n):
            Quote.objects.all().delete()
            return real_randrange(n)

        with patch("quotes.views.random.randrange", side_effect=delete_then_pick):
            response = self.client.get(RANDOM_URL)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "no_quotes_available")

    def test_unsupported_method_returns_json_error(self):
        for method in ("post", "put", "delete", "options"):
            response = getattr(self.client, method)(LIST_URL)
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response.json()["error"]["code"], "method_not_allowed")

    def test_auth_path_failure_returns_json_500(self):
        with patch.object(APIKey, "authenticate", side_effect=RuntimeError("db down")):
            response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "internal_error")
        self.assertNotIn("db down", response.content.decode())

    def test_unhandled_exception_returns_json_500_without_details(self):
        with patch("quotes.views.serialize_quote", side_effect=RuntimeError("secret")):
            response = self.client.get(RANDOM_URL)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                }
            },
        )
        self.assertNotIn("secret", response.content.decode())


class QuoteListAndDetailTests(TestCase):
    LIST_URL = "/api/v1/quotes/"

    def setUp(self):
        key = APIKey(name="test")
        raw_key = key.set_new_key()
        key.save()
        self.client.defaults["HTTP_X_API_KEY"] = raw_key

        self.dark_knight = Media.objects.create(
            title="The Dark Knight", media_type="MOVIE", release_year=2008
        )
        self.joker = Character.objects.create(name="The Joker", media=self.dark_knight)
        self.q1 = Quote.objects.create(
            text="Why so serious?", media=self.dark_knight, character=self.joker,
            language="en", tags=["villain", "classic"],
        )
        self.matrix = Media.objects.create(
            title="The Matrix", media_type="MOVIE", release_year=1999
        )
        self.q2 = Quote.objects.create(
            text="There is no spoon.", media=self.matrix, language="fr", tags=["sci-fi"],
        )

    def ids(self, query=""):
        response = self.client.get(f"{self.LIST_URL}{query}")
        self.assertEqual(response.status_code, 200)
        return [q["id"] for q in response.json()["results"]]

    def test_auth_required(self):
        client = Client()
        self.assertEqual(client.get(self.LIST_URL).status_code, 401)
        self.assertEqual(client.get(f"{self.LIST_URL}{self.q1.id}/").status_code, 401)

    def test_list_serialization_and_ordering(self):
        data = self.client.get(self.LIST_URL).json()

        self.assertEqual(data["count"], 2)
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])
        self.assertEqual([q["id"] for q in data["results"]], [self.q1.id, self.q2.id])
        self.assertEqual(
            data["results"][0]["media"],
            {"id": self.dark_knight.id, "title": "The Dark Knight",
             "media_type": "MOVIE", "release_year": 2008},
        )
        self.assertIsNone(data["results"][1]["character"])

    def test_empty_list(self):
        Quote.objects.all().delete()
        data = self.client.get(self.LIST_URL).json()
        self.assertEqual(data, {"count": 0, "next": None, "previous": None, "results": []})

    def test_pagination_links_and_page_size_cap(self):
        data = self.client.get(f"{self.LIST_URL}?page_size=1").json()
        self.assertEqual([q["id"] for q in data["results"]], [self.q1.id])
        self.assertEqual(data["next"], "/api/v1/quotes/?page_size=1&page=2")

        data = self.client.get(data["next"]).json()
        self.assertEqual([q["id"] for q in data["results"]], [self.q2.id])
        self.assertIsNone(data["next"])
        self.assertIn("page=1", data["previous"])

        self.assertEqual(len(self.ids("?page_size=1000")), 2)

    def test_invalid_pagination_params(self):
        for query in ["?page=0", "?page=abc", "?page=99", "?page_size=-1"]:
            response = self.client.get(f"{self.LIST_URL}{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(response.json()["error"]["code"], "invalid_parameters")

    def test_filters_and_search(self):
        self.assertEqual(self.ids("?media=dark"), [self.q1.id])
        self.assertEqual(self.ids("?character=JOKER"), [self.q1.id])
        self.assertEqual(self.ids("?year=1999"), [self.q2.id])
        self.assertEqual(self.ids("?language=fr"), [self.q2.id])
        self.assertEqual(self.ids("?tag=classic"), [self.q1.id])
        self.assertEqual(self.ids("?search=SERIOUS"), [self.q1.id])
        self.assertEqual(self.ids("?search=the&media=matrix"), [self.q2.id])
        self.assertEqual(self.ids("?search=the&year=2008&language=fr"), [])
        self.assertEqual(self.ids("?year=&tag="), [self.q1.id, self.q2.id])

    def test_invalid_filter_values(self):
        for query in ["?year=abc", "?language=NOT_A_CODE!"]:
            response = self.client.get(f"{self.LIST_URL}{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(response.json()["error"]["code"], "invalid_parameters")

    def test_detail(self):
        response = self.client.get(f"{self.LIST_URL}{self.q1.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["character"]["name"], "The Joker")
        self.assertEqual(response.json()["media"]["title"], "The Dark Knight")

        self.assertIsNone(self.client.get(f"{self.LIST_URL}{self.q2.id}/").json()["character"])

    def test_detail_not_found(self):
        response = self.client.get(f"{self.LIST_URL}99999/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "resource_not_found")


class APIDocumentationTests(TestCase):
    SCHEMA_URL = "/api/v1/openapi.json"
    DOCS_URL = "/api/v1/docs/"

    def spec(self):
        response = self.client.get(self.SCHEMA_URL)
        self.assertEqual(response.status_code, 200)
        return response.json()

    @staticmethod
    def normalize(path):
        # "/quotes/{id}/" and "quotes/<int:pk>/" both become "/quotes/{}/".
        return "/" + re.sub(r"<[^>]+>|\{[^}]+\}", "{}", path).lstrip("/")

    def test_schema_is_public_openapi_31_with_both_auth_schemes(self):
        spec = self.spec()
        self.assertTrue(spec["openapi"].startswith("3.1"))
        self.assertEqual(
            spec["components"]["securitySchemes"].keys(),
            {"ApiKeyHeader", "ApiKeyAuthorization"},
        )
        self.assertEqual(
            spec["components"]["securitySchemes"]["ApiKeyHeader"]["name"], "X-API-Key"
        )

    def test_docs_page_is_public_and_loads_the_schema(self):
        response = self.client.get(self.DOCS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-schema-url="{self.SCHEMA_URL}"')
        self.assertContains(response, 'integrity="sha384-')

    def test_docs_without_trailing_slash_redirects(self):
        response = self.client.get(self.DOCS_URL.rstrip("/"))
        self.assertRedirects(response, self.DOCS_URL, status_code=301)

    def test_docs_endpoints_are_read_only(self):
        for url in (self.SCHEMA_URL, self.DOCS_URL):
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_every_v1_route_is_documented(self):
        from . import api_urls

        undocumented_routes = {"not-found", "docs", "docs-redirect", "openapi"}
        documented = {self.normalize(path) for path in self.spec()["paths"]}
        routes = [
            p for p in api_urls.urlpatterns if p.name not in undocumented_routes
        ]
        self.assertTrue(routes)
        for pattern in routes:
            with self.subTest(route=pattern.name):
                self.assertIn(self.normalize(str(pattern.pattern)), documented)
        for url in DATA_URLS:
            with self.subTest(url=url):
                self.assertIn(
                    self.normalize(re.sub(r"/\d+/", "/{id}/", url[len("/api/v1"):])),
                    documented,
                )

    def test_data_operations_document_auth_errors(self):
        for path, operations in self.spec()["paths"].items():
            for method, operation in operations.items():
                with self.subTest(path=path, method=method):
                    self.assertIn("401", operation["responses"])
                    self.assertIn("403", operation["responses"])
                    self.assertIn("200", operation["responses"])

    def test_documented_page_size_matches_code(self):
        from .views import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

        param = self.spec()["components"]["parameters"]["page_size"]
        self.assertEqual(param["schema"]["default"], DEFAULT_PAGE_SIZE)
        # Larger values are reduced, not rejected, so the cap must not be a
        # schema maximum that client-side validation would enforce.
        self.assertNotIn("maximum", param["schema"])
        self.assertIn(f"reduced to {MAX_PAGE_SIZE}", param["description"])

    def test_documented_filters_match_list_endpoint(self):
        spec = self.spec()
        params = {
            spec["components"]["parameters"][ref["$ref"].rsplit("/", 1)[1]]["name"]
            for ref in spec["paths"]["/quotes/"]["get"]["parameters"]
        }
        self.assertEqual(
            params,
            {"page", "page_size", "search", "media", "character", "year", "language", "tag"},
        )

    def test_every_emitted_error_code_is_documented(self):
        from pathlib import Path

        source = "".join(
            (Path(__file__).parent / name).read_text(encoding="utf-8")
            for name in ("auth.py", "views.py")
        )
        codes = set(re.findall(r'api_error\(\s*"(\w+)"', source))
        self.assertIn("invalid_parameters", source)
        codes.add("invalid_parameters")  # raised through the _invalid() helper
        self.assertTrue(codes)
        spec_text = self.client.get(self.SCHEMA_URL).content.decode()
        for code in codes:
            with self.subTest(code=code):
                self.assertIn(f'"code": "{code}"', spec_text)


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

    def test_duplicate_name_is_rejected_when_media_is_read_only(self):
        Quote.objects.create(
            text="Hello", media=self.media, character=self.character, language="en"
        )
        Character.objects.create(name="Another", media=self.media)

        response = self.client.post(
            self.url, {"name": "Another", "_save": "Save"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["adminform"].form,
            "name",
            "A character with this name already exists for this media.",
        )
        self.character.refresh_from_db()
        self.assertEqual(self.character.name, "Speaker")

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
