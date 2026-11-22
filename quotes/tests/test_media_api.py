from django.test import Client, TestCase

from ..models import APIKey, Character, Media, Quote
from .helpers import MOVIES_URL, TV_SHOWS_URL


class MediaEndpointTests(TestCase):
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
        self.show = Media.objects.create(
            title="Breaking Bad", media_type="TV_SHOW", release_year=2008
        )
        self.joker = Character.objects.create(name="The Joker", media=self.dark_knight)
        Quote.objects.create(
            text="Why so serious?", media=self.dark_knight, character=self.joker,
            language="en",
        )

    def ids(self, url, query=""):
        response = self.client.get(f"{url}{query}")
        self.assertEqual(response.status_code, 200)
        return [m["id"] for m in response.json()["results"]]

    def test_auth_required(self):
        client = Client()
        for url in (MOVIES_URL, TV_SHOWS_URL, f"/api/v1/media/{self.matrix.id}/"):
            self.assertEqual(client.get(url).status_code, 401, url)

    def test_movie_and_tv_show_filtering(self):
        self.assertEqual(self.ids(MOVIES_URL), [self.dark_knight.id, self.matrix.id])
        self.assertEqual(self.ids(TV_SHOWS_URL), [self.show.id])
        self.assertEqual(
            self.client.get(MOVIES_URL).json()["results"][0],
            {"id": self.dark_knight.id, "title": "The Dark Knight",
             "media_type": "MOVIE", "release_year": 2008},
        )

    def test_title_search_and_year_filter(self):
        self.assertEqual(self.ids(MOVIES_URL, "?search=MATRIX"), [self.matrix.id])
        self.assertEqual(self.ids(MOVIES_URL, "?year=2008"), [self.dark_knight.id])
        self.assertEqual(self.ids(TV_SHOWS_URL, "?year=2008"), [self.show.id])
        self.assertEqual(self.ids(MOVIES_URL, "?search=the&year=1999"), [self.matrix.id])
        self.assertEqual(self.ids(MOVIES_URL, "?search=breaking"), [])
        self.assertEqual(self.ids(MOVIES_URL, "?year=&search="), [self.dark_knight.id, self.matrix.id])

    def test_invalid_year(self):
        response = self.client.get(f"{MOVIES_URL}?year=abc")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_parameters")

    def test_ordering(self):
        dk, mx = self.dark_knight.id, self.matrix.id
        self.assertEqual(self.ids(MOVIES_URL, "?ordering=-id"), [mx, dk])
        self.assertEqual(self.ids(MOVIES_URL, "?ordering=title"), [dk, mx])
        self.assertEqual(self.ids(MOVIES_URL, "?ordering=-title"), [mx, dk])
        self.assertEqual(self.ids(MOVIES_URL, "?ordering=year"), [mx, dk])
        self.assertEqual(self.ids(MOVIES_URL, "?ordering=-year"), [dk, mx])
        self.assertEqual(self.ids(TV_SHOWS_URL, "?ordering=-year"), [self.show.id])

    def test_ordering_tie_breaker(self):
        other = Media.objects.create(title="Other", media_type="MOVIE", release_year=2008)
        self.assertEqual(
            self.ids(MOVIES_URL, "?ordering=year"), [self.matrix.id, self.dark_knight.id, other.id]
        )
        self.assertEqual(
            self.ids(MOVIES_URL, "?ordering=-year"), [other.id, self.dark_knight.id, self.matrix.id]
        )

    def test_unknown_ordering(self):
        response = self.client.get(f"{MOVIES_URL}?ordering=name")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_parameters")
        self.assertIn("title", response.json()["error"]["message"])

    def test_query_count_is_constant(self):
        with self.assertNumQueries(5):
            self.client.get(f"{MOVIES_URL}?ordering=-year")
        for i in range(10):
            Media.objects.create(title=f"M{i}", media_type="MOVIE", release_year=2010)
        with self.assertNumQueries(5):
            self.client.get(f"{MOVIES_URL}?ordering=-year")

    def test_pagination(self):
        data = self.client.get(f"{MOVIES_URL}?page_size=1").json()
        self.assertEqual(data["count"], 2)
        self.assertEqual([m["id"] for m in data["results"]], [self.dark_knight.id])
        self.assertEqual(data["next"], "/api/v1/media/movies/?page_size=1&page=2")
        data = self.client.get(data["next"]).json()
        self.assertEqual([m["id"] for m in data["results"]], [self.matrix.id])
        self.assertIsNone(data["next"])
        self.assertEqual(self.client.get(f"{MOVIES_URL}?page=99").status_code, 400)

    def test_detail_includes_characters_but_not_quotes(self):
        data = self.client.get(f"/api/v1/media/{self.dark_knight.id}/").json()
        self.assertEqual(data["title"], "The Dark Knight")
        self.assertEqual(data["media_type"], "MOVIE")
        self.assertEqual(data["release_year"], 2008)
        self.assertEqual(data["characters"], [{"id": self.joker.id, "name": "The Joker"}])
        self.assertNotIn("quotes", data)

    def test_detail_works_for_tv_show(self):
        data = self.client.get(f"/api/v1/media/{self.show.id}/").json()
        self.assertEqual(data["media_type"], "TV_SHOW")
        self.assertEqual(data["characters"], [])

    def test_detail_not_found(self):
        response = self.client.get("/api/v1/media/99999/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "resource_not_found")
