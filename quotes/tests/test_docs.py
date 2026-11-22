import re

from django.test import TestCase

from .helpers import DATA_URLS


class APIDocumentationTests(TestCase):
    SCHEMA_URL = "/api/v1/openapi.json"
    DOCS_URL = "/api/v1/docs/"

    def spec(self):
        response = self.client.get(self.SCHEMA_URL)
        self.assertEqual(response.status_code, 200)
        return response.json()

    @staticmethod
    def normalize(path):
        # "/quotes/{id}/" and "quotes/<int:pk>/" both become "/quotes/{}/".
        return "/" + re.sub(r"<[^>]+>|\{[^}]+\}", "{}", path).lstrip("/")

    def test_schema_is_public_openapi_31_with_both_auth_schemes(self):
        spec = self.spec()
        self.assertTrue(spec["openapi"].startswith("3.1"))
        self.assertEqual(
            spec["components"]["securitySchemes"].keys(),
            {"ApiKeyHeader", "ApiKeyAuthorization"},
        )
        self.assertEqual(
            spec["components"]["securitySchemes"]["ApiKeyHeader"]["name"], "X-API-Key"
        )

    def test_docs_page_is_public_and_loads_the_schema(self):
        response = self.client.get(self.DOCS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-schema-url="{self.SCHEMA_URL}"')
        self.assertContains(response, 'integrity="sha384-')

    def test_docs_without_trailing_slash_redirects(self):
        response = self.client.get(self.DOCS_URL.rstrip("/"))
        self.assertRedirects(response, self.DOCS_URL, status_code=301)

    def test_docs_endpoints_are_read_only(self):
        for url in (self.SCHEMA_URL, self.DOCS_URL):
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_every_v1_route_is_documented(self):
        from .. import api_urls

        undocumented_routes = {"not-found", "docs", "docs-redirect", "openapi"}
        documented = {self.normalize(path) for path in self.spec()["paths"]}
        routes = [
            p for p in api_urls.urlpatterns if p.name not in undocumented_routes
        ]
        self.assertTrue(routes)
        for pattern in routes:
            with self.subTest(route=pattern.name):
                self.assertIn(self.normalize(str(pattern.pattern)), documented)
        for url in DATA_URLS:
            with self.subTest(url=url):
                self.assertIn(
                    self.normalize(re.sub(r"/\d+/", "/{id}/", url[len("/api/v1"):])),
                    documented,
                )

    def test_data_operations_document_auth_errors(self):
        for path, operations in self.spec()["paths"].items():
            for method, operation in operations.items():
                with self.subTest(path=path, method=method):
                    self.assertIn("401", operation["responses"])
                    self.assertIn("403", operation["responses"])
                    self.assertIn("200", operation["responses"])

    def test_documented_page_size_matches_code(self):
        from ..views import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

        param = self.spec()["components"]["parameters"]["page_size"]
        self.assertEqual(param["schema"]["default"], DEFAULT_PAGE_SIZE)
        # Larger values are reduced, not rejected, so the cap must not be a
        # schema maximum that client-side validation would enforce.
        self.assertNotIn("maximum", param["schema"])
        self.assertIn(f"reduced to {MAX_PAGE_SIZE}", param["description"])

    def test_documented_filters_match_list_endpoint(self):
        spec = self.spec()
        params = {
            spec["components"]["parameters"][ref["$ref"].rsplit("/", 1)[1]]["name"]
            for ref in spec["paths"]["/quotes/"]["get"]["parameters"]
        }
        self.assertEqual(
            params,
            {
                "page", "page_size", "ordering", "search", "media", "media_id",
                "character", "year", "language", "tag",
            },
        )

    def test_every_emitted_error_code_is_documented(self):
        from pathlib import Path

        source = "".join(
            (Path(__file__).parent.parent / name).read_text(encoding="utf-8")
            for name in ("auth.py", "views.py")
        )
        codes = set(re.findall(r'api_error\(\s*"(\w+)"', source))
        self.assertIn("invalid_parameters", source)
        codes.add("invalid_parameters")  # raised through the _invalid() helper
        self.assertTrue(codes)
        spec_text = self.client.get(self.SCHEMA_URL).content.decode()
        for code in codes:
            with self.subTest(code=code):
                self.assertIn(f'"code": "{code}"', spec_text)
