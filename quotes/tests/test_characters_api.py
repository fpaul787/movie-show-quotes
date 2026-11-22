from django.test import Client, TestCase

from ..models import APIKey, Character, Media, Quote
from .helpers import CHARACTERS_URL


class CharacterEndpointTests(TestCase):
    def setUp(self):
        key = APIKey(name="test")
        raw_key = key.set_new_key()
        key.save()
        self.client.defaults["HTTP_X_API_KEY"] = raw_key

        self.dark_knight = Media.objects.create(
            title="The Dark Knight", media_type="MOVIE", release_year=2008
        )
        self.matrix = Media.objects.create(
            title="The Matrix", media_type="MOVIE", release_year=1999
        )
        self.joker = Character.objects.create(name="The Joker", media=self.dark_knight)
        self.batman = Character.objects.create(name="Batman", media=self.dark_knight)
        self.neo = Character.objects.create(name="Neo", media=self.matrix)
        for text in ("Why so serious?", "Introduce a little anarchy."):
            Quote.objects.create(
                text=text, media=self.dark_knight, character=self.joker, language="en"
            )

    def ids(self, query=""):
        response = self.client.get(f"{CHARACTERS_URL}{query}")
        self.assertEqual(response.status_code, 200)
        return [c["id"] for c in response.json()["results"]]

    def test_auth_required(self):
        client = Client()
        self.assertEqual(client.get(CHARACTERS_URL).status_code, 401)
        self.assertEqual(client.get(f"{CHARACTERS_URL}{self.joker.id}/").status_code, 401)

    def test_list_serialization(self):
        data = self.client.get(CHARACTERS_URL).json()
        self.assertEqual(data["count"], 3)
        self.assertEqual(
            data["results"][0],
            {
                "id": self.joker.id,
                "name": "The Joker",
                "media": {
                    "id": self.dark_knight.id,
                    "title": "The Dark Knight",
                    "media_type": "MOVIE",
                    "release_year": 2008,
                },
            },
        )

    def test_search_and_media_id(self):
        self.assertEqual(self.ids("?search=JOKER"), [self.joker.id])
        self.assertEqual(
            self.ids(f"?media_id={self.dark_knight.id}"), [self.joker.id, self.batman.id]
        )
        self.assertEqual(self.ids(f"?media_id={self.matrix.id}&search=bat"), [])

    def test_invalid_media_id(self):
        response = self.client.get(f"{CHARACTERS_URL}?media_id=abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_parameters")

    def test_ordering(self):
        j, b, n = self.joker.id, self.batman.id, self.neo.id
        self.assertEqual(self.ids("?ordering=-id"), [n, b, j])
        self.assertEqual(self.ids("?ordering=name"), [b, n, j])
        self.assertEqual(self.ids("?ordering=-name"), [j, n, b])

    def test_unknown_ordering(self):
        response = self.client.get(f"{CHARACTERS_URL}?ordering=year")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_parameters")
        self.assertIn("name", response.json()["error"]["message"])

    def test_pagination(self):
        data = self.client.get(f"{CHARACTERS_URL}?page_size=2").json()
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data["next"], "/api/v1/characters/?page_size=2&page=2")
        data = self.client.get(data["next"]).json()
        self.assertEqual([c["id"] for c in data["results"]], [self.neo.id])
        self.assertIsNone(data["next"])

    def test_empty_result(self):
        data = self.client.get(f"{CHARACTERS_URL}?search=nobody").json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])

    def test_query_count_is_constant(self):
        with self.assertNumQueries(5):
            self.client.get(CHARACTERS_URL)
        for i in range(10):
            Character.objects.create(name=f"C{i}", media=self.matrix)
        with self.assertNumQueries(5):
            self.client.get(CHARACTERS_URL)

    def test_detail(self):
        data = self.client.get(f"{CHARACTERS_URL}{self.joker.id}/").json()
        self.assertEqual(data["name"], "The Joker")
        self.assertEqual(data["media"]["title"], "The Dark Knight")
        self.assertEqual(data["quote_count"], 2)
        self.assertNotIn("quotes", data)
        self.assertEqual(self.client.get(f"{CHARACTERS_URL}{self.neo.id}/").json()["quote_count"], 0)

    def test_detail_not_found(self):
        response = self.client.get(f"{CHARACTERS_URL}99999/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "resource_not_found")

    def test_detail_query_count(self):
        with self.assertNumQueries(4):
            self.client.get(f"{CHARACTERS_URL}{self.joker.id}/")
