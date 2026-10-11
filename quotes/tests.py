from django.test import TestCase


class QuoteEndpointTests(TestCase):
    def test_quote_returns_hello_world_json(self):
        response = self.client.get("/quote")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Hello World"})
