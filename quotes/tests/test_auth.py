from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from ..models import APIKey
from .helpers import RANDOM_URL, DATA_URLS


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

    def test_write_methods_return_json_405_with_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        headers = {"X-API-Key": self.raw_key}
        for url in DATA_URLS:
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(url=url, method=method):
                    response = getattr(client, method)(url, headers=headers)
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(response["Content-Type"], "application/json")

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
