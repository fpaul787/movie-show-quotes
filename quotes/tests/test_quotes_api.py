from django.test import Client, TestCase

from ..models import APIKey, Character, Media, Quote
from .helpers import RANDOM_URL, LIST_URL


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

    def _two_quotes(self):
        dk = Media.objects.create(title="The Dark Knight", media_type="MOVIE", release_year=2008)
        joker = Character.objects.create(name="The Joker", media=dk)
        mx = Media.objects.create(title="The Matrix", media_type="MOVIE", release_year=1999)
        q1 = Quote.objects.create(
            text="Why so serious?", media=dk, character=joker, language="en", tags=["classic"]
        )
        q2 = Quote.objects.create(text="There is no spoon.", media=mx, language="fr", tags=["sci-fi"])
        return dk, mx, q1, q2

    def test_random_filters_narrow_results(self):
        dk, mx, q1, q2 = self._two_quotes()
        for query, expected in (
            ("media=matrix", q2), (f"media_id={dk.id}", q1), ("character=joker", q1),
            ("year=1999", q2), ("language=fr", q2), ("tag=CLASSIC", q1), ("search=spoon", q2),
        ):
            for _ in range(5):
                response = self.client.get(f"{RANDOM_URL}?{query}")
                self.assertEqual(response.status_code, 200, query)
                self.assertEqual(response.json()["id"], expected.id, query)

    def test_random_invalid_filters_return_400(self):
        self._two_quotes()
        for query in ("year=abc", "media_id=0", "language=NOT_A_CODE!"):
            response = self.client.get(f"{RANDOM_URL}?{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(response.json()["error"]["code"], "invalid_parameters")

    def test_random_no_match_returns_no_quotes_available(self):
        self._two_quotes()
        response = self.client.get(f"{RANDOM_URL}?year=1800")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "no_quotes_available")

    def test_random_ignores_pagination_and_ordering(self):
        self._two_quotes()
        response = self.client.get(f"{RANDOM_URL}?page=99&page_size=abc&ordering=bogus")
        self.assertEqual(response.status_code, 200)


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
        self.assertEqual(self.ids("?language=FR"), [self.q2.id])
        self.assertEqual(self.ids("?tag=classic"), [self.q1.id])
        self.assertEqual(self.ids("?tag=Classic"), [self.q1.id])
        self.assertEqual(self.ids(f"?media_id={self.matrix.id}"), [self.q2.id])
        self.assertEqual(self.ids(f"?media_id={self.matrix.id}&media=matrix"), [self.q2.id])
        self.assertEqual(self.ids(f"?media_id={self.matrix.id}&media=dark"), [])
        self.assertEqual(self.ids("?media_id="), [self.q1.id, self.q2.id])
        self.assertEqual(self.ids("?search=SERIOUS"), [self.q1.id])
        self.assertEqual(self.ids("?search=the&media=matrix"), [self.q2.id])
        self.assertEqual(self.ids("?search=the&year=2008&language=fr"), [])
        self.assertEqual(self.ids("?year=&tag="), [self.q1.id, self.q2.id])

    def test_invalid_filter_values(self):
        for query in ["?year=abc", "?language=NOT_A_CODE!", "?media_id=abc", "?media_id=0",
                      "?ordering=bogus", "?ordering=-"]:
            response = self.client.get(f"{self.LIST_URL}{query}")
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(response.json()["error"]["code"], "invalid_parameters")

    def test_ordering(self):
        a, b = self.q1.id, self.q2.id  # q1: Dark Knight 2008, q2: Matrix 1999
        self.assertEqual(self.ids("?ordering=id"), [a, b])
        self.assertEqual(self.ids("?ordering=-id"), [b, a])
        self.assertEqual(self.ids("?ordering=title"), [a, b])
        self.assertEqual(self.ids("?ordering=-title"), [b, a])
        self.assertEqual(self.ids("?ordering=year"), [b, a])
        self.assertEqual(self.ids("?ordering=-year"), [a, b])

    def test_ordering_unknown_value_lists_allowed_values(self):
        message = self.client.get(f"{self.LIST_URL}?ordering=text").json()["error"]["message"]
        for name in ("id", "title", "year"):
            self.assertIn(name, message)

    def test_ordering_tie_breaker_keeps_pages_stable(self):
        extra = [
            Quote.objects.create(text=f"x{i}", media=self.matrix, language="en")
            for i in range(4)
        ]
        expected = sorted([self.q2.id] + [q.id for q in extra], reverse=True) + [self.q1.id]
        expected = [i for i in expected if i != self.q1.id]
        collected = []
        url = f"{self.LIST_URL}?ordering=-year&page_size=2"
        # -year puts the Dark Knight quote first, then Matrix quotes by descending id.
        data = self.client.get(url).json()
        collected += [q["id"] for q in data["results"]]
        while data["next"]:
            data = self.client.get(data["next"]).json()
            collected += [q["id"] for q in data["results"]]
        self.assertEqual(collected, [self.q1.id] + expected)

    def test_query_count_is_constant(self):
        with self.assertNumQueries(5):
            self.client.get(f"{self.LIST_URL}?ordering=-title")
        for i in range(10):
            Quote.objects.create(text=f"y{i}", media=self.matrix, language="en")
        with self.assertNumQueries(5):
            self.client.get(f"{self.LIST_URL}?ordering=-title")

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
