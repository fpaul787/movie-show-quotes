import random
from unittest.mock import patch

from django.test import TestCase

from ..models import APIKey, Character, Media, Quote
from .helpers import RANDOM_URL, LIST_URL


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
        # One auth lookup, one rate-limit upsert, one last_used update, count,
        # and the quote itself.
        with self.assertNumQueries(5):
            self.assertEqual(self.client.get(RANDOM_URL).status_code, 200)

    def test_list_query_count_does_not_grow_with_results(self):
        with self.assertNumQueries(5):
            self.assertEqual(self.client.get(LIST_URL).status_code, 200)

    def test_filtered_list_query_count_is_constant(self):
        with self.assertNumQueries(5):
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
