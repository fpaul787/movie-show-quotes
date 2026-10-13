from django.test import TestCase

from .models import Quote


class QuoteEndpointTests(TestCase):
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

        response = self.client.get("/quote")

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
            self.assertIn(self.client.get("/quote").json()["text"], texts)

    def test_quote_does_not_create_quotes(self):
        self.client.get("/quote")

        self.assertEqual(Quote.objects.count(), 0)

    def test_quote_returns_404_when_no_quotes_exist(self):
        response = self.client.get("/quote")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "No quotes available"})
