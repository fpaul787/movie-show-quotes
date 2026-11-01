from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import APIKey, Quote


class HomepageTests(TestCase):
    def test_root_serves_react_homepage(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"></div>', html=False)

    def test_legacy_homepage_url_redirects_to_root(self):
        response = self.client.get("/homepage/")

        self.assertRedirects(
            response, "/", status_code=301, fetch_redirect_response=False
        )

    def test_signup_page_serves_the_react_app(self):
        response = self.client.get("/signup/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"></div>', html=False)


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
