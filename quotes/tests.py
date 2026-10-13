from django.test import TestCase

from .models import Quote


class QuoteEndpointTests(TestCase):
    def test_quote_returns_quote_as_json(self):
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

    def test_quote_endpoint_does_not_create_duplicate_quotes(self):
        self.client.get("/quote")
        self.client.get("/quote")

        self.assertEqual(Quote.objects.count(), 1)
