from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import APIKey, Quote


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
        Quote.objects.create(
            text="May the Force be with you.",
            year=1977,
            title="Star Wars",
            character="Han Solo",
            source="Movie",
            language="English",
            tags=["classic", "sci-fi"],
            created_at="1977-05-25",
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
                "language": "English",
                "tags": ["classic", "sci-fi"],
                "created_at": "1977-05-25",
            },
        )

    def test_quote_returns_one_of_the_stored_quotes(self):
        for i in range(5):
            Quote.objects.create(
                text=f"Quote {i}",
                year=2000 + i,
                title=f"Title {i}",
                character="Someone",
                source="Movie",
                language="English",
                tags=[],
                created_at="2000-01-01",
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
