"""Hand-maintained OpenAPI 3.1 description of the /api/v1/ endpoints.

Served at /api/v1/openapi.json and rendered at /api/v1/docs/. When adding or
changing an endpoint, update this module too; the documentation tests fail if
a named api_v1 route is missing here.
"""

DESCRIPTION = """\
Read-only access to quotes from movies and TV shows.

## Quick start

1. Sign up, then create your API key at `/profile/api-keys/`. The full key is
   shown **once**; store it somewhere safe.
2. Send the key with every request:

```sh
curl -H "X-API-Key: <your-key>" https://<host>/api/v1/quotes/random/
```

## Authentication

Every data endpoint requires an API key, sent in either header:

- `X-API-Key: <your-key>`
- `Authorization: Api-Key <your-key>`

Keys are read-only: `POST`, `PUT`, `PATCH` and `DELETE` return `405`.

## Errors

Errors always use this shape, with a stable machine-readable `code`:

```json
{"error": {"code": "invalid_api_key", "message": "The provided API key is invalid."}}
```

| Status | Codes |
|---|---|
| 400 | `invalid_parameters` |
| 401 | `missing_api_key`, `invalid_api_key` |
| 403 | `revoked_api_key`, `expired_api_key` |
| 404 | `resource_not_found`, `no_quotes_available` |
| 405 | `method_not_allowed` |
| 429 | `rate_limit_exceeded` |

## Rate limits

Each API key is limited to __RATE_LIMIT_PER_MINUTE__ per calendar minute and
__RATE_LIMIT_PER_DAY__ per calendar day (both UTC, fixed windows). Requests with
a missing, invalid, revoked or expired key are not counted; every other request
is, including ones rejected with `429` or `405`. Over a limit, the API returns
`429` with `Retry-After` (whole seconds until the exhausted window resets; the
daily reset if the daily limit is exhausted).

Authenticated responses include:

| Header | Value |
|---|---|
| `X-RateLimit-Limit` | Requests allowed per minute |
| `X-RateLimit-Remaining` | Requests left in the current minute |
| `X-RateLimit-Reset` | Unix timestamp when the current minute resets |

The limits are configurable per deployment; a disabled per-minute limit omits
the `X-RateLimit-*` headers. The documentation endpoints are not rate limited.

## Pagination

Collection endpoints are paginated with `page` (starting at 1) and
`page_size` (default __DEFAULT_PAGE_SIZE__, maximum __MAX_PAGE_SIZE__; larger values
are reduced to __MAX_PAGE_SIZE__). Results are ordered by `id` by default, or by
`ordering` (`id`, `title`, `year`; prefix `-` for descending), always with `id` as
the final tie-breaker, so pages are stable.
Responses include the total `count` and `next` / `previous` links (relative URLs,
or `null`). Requesting a page past the last one returns `400`.

## Filtering and search

Filters are optional query parameters and are combined with AND. Blank values
(e.g. `?year=`) are ignored, as are unknown parameters.
"""


def _limit_text(limit):
    return f"{limit} requests" if limit > 0 else "an unlimited number of requests"


def _error(code, message):
    return {"error": {"code": code, "message": message}}


def _error_response(description, examples):
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Error"},
                "examples": {
                    code: {"value": _error(code, message)}
                    for code, message in examples
                },
            }
        },
    }


def _query_param(name, description, schema, example=None):
    param = {
        "name": name,
        "in": "query",
        "required": False,
        "description": description,
        "schema": schema,
    }
    if example is not None:
        param["example"] = example
    return param


EXAMPLE_QUOTE = {
    "id": 123,
    "text": "Why so serious?",
    "language": "en",
    "tags": ["villain", "classic"],
    "character": {"id": 10, "name": "The Joker"},
    "media": {
        "id": 5,
        "title": "The Dark Knight",
        "media_type": "MOVIE",
        "release_year": 2008,
    },
}

EXAMPLE_QUOTE_NO_CHARACTER = {
    "id": 124,
    "text": "There is no spoon.",
    "language": "en",
    "tags": ["sci-fi"],
    "character": None,
    "media": {
        "id": 6,
        "title": "The Matrix",
        "media_type": "MOVIE",
        "release_year": 1999,
    },
}

EXAMPLE_MEDIA_DETAIL = {
    **EXAMPLE_QUOTE["media"],
    "characters": [{"id": 10, "name": "The Joker"}],
}

EXAMPLE_CHARACTER = {"id": 10, "name": "The Joker", "media": EXAMPLE_QUOTE["media"]}

AUTH_RESPONSES = {
    "401": {"$ref": "#/components/responses/Unauthorized"},
    "403": {"$ref": "#/components/responses/Forbidden"},
    "405": {"$ref": "#/components/responses/MethodNotAllowed"},
    "429": {"$ref": "#/components/responses/RateLimited"},
    "500": {"$ref": "#/components/responses/InternalError"},
}

RATE_LIMIT_HEADERS = {
    "X-RateLimit-Limit": {"$ref": "#/components/headers/X-RateLimit-Limit"},
    "X-RateLimit-Remaining": {"$ref": "#/components/headers/X-RateLimit-Remaining"},
    "X-RateLimit-Reset": {"$ref": "#/components/headers/X-RateLimit-Reset"},
}


def _media_list_path(tag, operation_id, summary, media_type):
    kind = "movies" if media_type == "MOVIE" else "TV shows"
    return {
        "get": {
            "tags": [tag],
            "operationId": operation_id,
            "summary": summary,
            "description": (
                f"Returns a paginated collection of {kind}, ordered by `id` unless `ordering` is given. "
                "Filter by title with `search` and by `year`; they are ANDed together."
            ),
            "parameters": [
                {"$ref": f"#/components/parameters/{name}"}
                for name in ("page", "page_size", "ordering", "media_search", "year")
            ],
            "responses": {
                "200": {
                    "description": f"A page of {kind}.",
                    "headers": RATE_LIMIT_HEADERS,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/MediaPage"},
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/BadRequest"},
                **AUTH_RESPONSES,
            },
        }
    }


def build_openapi_spec():
    from django.conf import settings

    # Imported here to avoid a circular import (views serves this spec).
    from .views import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

    quote_ref = {"$ref": "#/components/schemas/Quote"}

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Movie Show Quotes API",
            "version": "1.0.0",
            "description": DESCRIPTION.replace(
                "__DEFAULT_PAGE_SIZE__", str(DEFAULT_PAGE_SIZE)
            )
            .replace("__MAX_PAGE_SIZE__", str(MAX_PAGE_SIZE))
            .replace("__RATE_LIMIT_PER_MINUTE__", _limit_text(settings.API_RATE_LIMIT_PER_MINUTE))
            .replace("__RATE_LIMIT_PER_DAY__", _limit_text(settings.API_RATE_LIMIT_PER_DAY)),
        },
        "servers": [{"url": "/api/v1"}],
        "security": [{"ApiKeyHeader": []}, {"ApiKeyAuthorization": []}],
        "tags": [
            {"name": "Quotes", "description": "Retrieve, filter and search quotes."},
            {"name": "Media", "description": "Retrieve movies and TV shows."},
            {"name": "Characters", "description": "Retrieve characters."},
        ],
        "paths": {
            "/quotes/": {
                "get": {
                    "tags": ["Quotes"],
                    "operationId": "listQuotes",
                    "summary": "List quotes",
                    "description": (
                        "Returns a paginated collection of quotes, ordered by `id` unless "
                        "`ordering` is given. "
                        "Combine any of the filters and `search`; they are ANDed together.\n\n"
                        "Example: `GET /api/v1/quotes/?search=serious&year=2008&page_size=10`"
                    ),
                    "parameters": [
                        {"$ref": f"#/components/parameters/{name}"}
                        for name in (
                            "page", "page_size", "ordering", "search", "media", "media_id",
                            "character", "year", "language", "tag",
                        )
                    ],
                    "responses": {
                        "200": {
                            "description": "A page of quotes.",
                            "headers": RATE_LIMIT_HEADERS,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/QuotePage"},
                                    "examples": {
                                        "page": {
                                            "summary": "First page of two",
                                            "value": {
                                                "count": 2,
                                                "next": "/api/v1/quotes/?page_size=1&page=2",
                                                "previous": None,
                                                "results": [EXAMPLE_QUOTE],
                                            },
                                        },
                                        "empty": {
                                            "summary": "No matching quotes",
                                            "value": {
                                                "count": 0,
                                                "next": None,
                                                "previous": None,
                                                "results": [],
                                            },
                                        },
                                    },
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        **AUTH_RESPONSES,
                    },
                }
            },
            "/quotes/random/": {
                "get": {
                    "tags": ["Quotes"],
                    "operationId": "getRandomQuote",
                    "summary": "Get a random quote",
                    "description": (
                        "Returns one quote chosen at random. Accepts the same filters as the "
                        "list endpoint (`media`, `media_id`, `character`, `year`, `language`, "
                        "`tag`, `search`). `page`, `page_size` and `ordering` are ignored."
                    ),
                    "parameters": [
                        {"$ref": f"#/components/parameters/{name}"}
                        for name in (
                            "search", "media", "media_id", "character", "year",
                            "language", "tag",
                        )
                    ],
                    "responses": {
                        "200": {
                            "description": "A random quote.",
                            "headers": RATE_LIMIT_HEADERS,
                            "content": {
                                "application/json": {
                                    "schema": quote_ref,
                                    "examples": {
                                        "quote": {"value": EXAMPLE_QUOTE},
                                        "unknownSpeaker": {
                                            "summary": "Speaker unknown",
                                            "value": EXAMPLE_QUOTE_NO_CHARACTER,
                                        },
                                    },
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "404": _error_response(
                            "No quote matches the filters, or there are no quotes.",
                            [("no_quotes_available", "No quotes available.")],
                        ),
                        **AUTH_RESPONSES,
                    },
                }
            },
            "/quotes/{id}/": {
                "get": {
                    "tags": ["Quotes"],
                    "operationId": "getQuote",
                    "summary": "Get a quote by ID",
                    "description": "Returns one quote, in the same shape used by the list endpoint.",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "The quote's `id`.",
                            "schema": {"type": "integer", "minimum": 0},
                            "example": 123,
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "The quote.",
                            "headers": RATE_LIMIT_HEADERS,
                            "content": {
                                "application/json": {
                                    "schema": quote_ref,
                                    "example": EXAMPLE_QUOTE,
                                }
                            },
                        },
                        "404": {"$ref": "#/components/responses/NotFound"},
                        **AUTH_RESPONSES,
                    },
                }
            },
            "/media/movies/": _media_list_path("Media", "listMovies", "List movies", "MOVIE"),
            "/media/tv-shows/": _media_list_path(
                "Media", "listTvShows", "List TV shows", "TV_SHOW"
            ),
            "/media/{id}/": {
                "get": {
                    "tags": ["Media"],
                    "operationId": "getMedia",
                    "summary": "Get a movie or TV show by ID",
                    "description": (
                        "Returns one movie or TV show with its characters. "
                        "Quotes are not included; use `GET /quotes/?media=<title>`."
                    ),
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "The media's `id`.",
                            "schema": {"type": "integer", "minimum": 0},
                            "example": 5,
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "The movie or TV show.",
                            "headers": RATE_LIMIT_HEADERS,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/MediaDetail"},
                                    "example": EXAMPLE_MEDIA_DETAIL,
                                }
                            },
                        },
                        "404": {"$ref": "#/components/responses/NotFound"},
                        **AUTH_RESPONSES,
                    },
                }
            },
            "/media/{id}/quotes/": {
                "get": {
                    "tags": ["Media"],
                    "operationId": "listMediaQuotes",
                    "summary": "List quotes for a movie or TV show",
                    "description": (
                        "Returns the same paginated quotes as `GET /quotes/`, limited to this "
                        "media item. Supports the same filters except `media` and `media_id`, "
                        "plus `ordering`."
                    ),
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "The media's `id`.",
                            "schema": {"type": "integer", "minimum": 0},
                            "example": 5,
                        },
                        *(
                            {"$ref": f"#/components/parameters/{name}"}
                            for name in (
                                "page", "page_size", "ordering", "search", "character",
                                "year", "language", "tag",
                            )
                        ),
                    ],
                    "responses": {
                        "200": {
                            "description": "A page of quotes.",
                            "headers": RATE_LIMIT_HEADERS,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/QuotePage"},
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        "404": {"$ref": "#/components/responses/NotFound"},
                        **AUTH_RESPONSES,
                    },
                }
            },
            "/characters/": {
                "get": {
                    "tags": ["Characters"],
                    "operationId": "listCharacters",
                    "summary": "List characters",
                    "description": (
                        "Returns a paginated collection of characters, ordered by `id` unless "
                        "`ordering` is given. Filter by name with `search` and by `media_id`; "
                        "they are ANDed together."
                    ),
                    "parameters": [
                        {"$ref": f"#/components/parameters/{name}"}
                        for name in (
                            "page", "page_size", "character_ordering", "character_search",
                            "media_id",
                        )
                    ],
                    "responses": {
                        "200": {
                            "description": "A page of characters.",
                            "headers": RATE_LIMIT_HEADERS,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CharacterPage"},
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/BadRequest"},
                        **AUTH_RESPONSES,
                    },
                }
            },
            "/characters/{id}/": {
                "get": {
                    "tags": ["Characters"],
                    "operationId": "getCharacter",
                    "summary": "Get a character by ID",
                    "description": (
                        "Returns one character with its media and `quote_count`. Quotes are not "
                        "included; use `GET /quotes/?character=<name>` or `GET /media/{id}/quotes/`."
                    ),
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "description": "The character's `id`.",
                            "schema": {"type": "integer", "minimum": 0},
                            "example": 10,
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "The character.",
                            "headers": RATE_LIMIT_HEADERS,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CharacterDetail"},
                                    "example": {**EXAMPLE_CHARACTER, "quote_count": 3},
                                }
                            },
                        },
                        "404": {"$ref": "#/components/responses/NotFound"},
                        **AUTH_RESPONSES,
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "ApiKeyHeader": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "Send your key as `X-API-Key: <your-key>`.",
                },
                "ApiKeyAuthorization": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": (
                        "Send your key as `Authorization: Api-Key <your-key>`. "
                        "When using this scheme in the docs UI, enter `Api-Key <your-key>`."
                    ),
                },
            },
            "schemas": {
                "Media": {
                    "type": "object",
                    "description": "The movie or TV show a quote comes from.",
                    "required": ["id", "title", "media_type", "release_year"],
                    "properties": {
                        "id": {"type": "integer"},
                        "title": {"type": "string"},
                        "media_type": {"type": "string", "enum": ["MOVIE", "TV_SHOW"]},
                        "release_year": {"type": "integer", "description": "Original release year."},
                    },
                    "example": EXAMPLE_QUOTE["media"],
                },
                "Character": {
                    "type": "object",
                    "description": "The character who says the quote.",
                    "required": ["id", "name"],
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                    "example": EXAMPLE_QUOTE["character"],
                },
                "Quote": {
                    "type": "object",
                    "required": ["id", "text", "language", "tags", "character", "media"],
                    "properties": {
                        "id": {"type": "integer"},
                        "text": {"type": "string"},
                        "language": {
                            "type": "string",
                            "description": "ISO 639 language code, e.g. `en` or `pt-BR`.",
                        },
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "character": {
                            "description": "`null` when the speaker is unknown.",
                            "oneOf": [
                                {"$ref": "#/components/schemas/Character"},
                                {"type": "null"},
                            ],
                        },
                        "media": {"$ref": "#/components/schemas/Media"},
                    },
                    "example": EXAMPLE_QUOTE,
                },
                "QuotePage": {
                    "type": "object",
                    "required": ["count", "next", "previous", "results"],
                    "properties": {
                        "count": {
                            "type": "integer",
                            "description": "Total number of quotes matching the filters, across all pages.",
                        },
                        "next": {
                            "type": ["string", "null"],
                            "description": "Relative URL of the next page, keeping your filters; `null` on the last page.",
                        },
                        "previous": {
                            "type": ["string", "null"],
                            "description": "Relative URL of the previous page; `null` on the first page.",
                        },
                        "results": {"type": "array", "items": quote_ref},
                    },
                },
                "MediaDetail": {
                    "description": "A movie or TV show with its characters.",
                    "allOf": [
                        {"$ref": "#/components/schemas/Media"},
                        {
                            "type": "object",
                            "required": ["characters"],
                            "properties": {
                                "characters": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Character"},
                                }
                            },
                        },
                    ],
                    "example": EXAMPLE_MEDIA_DETAIL,
                },
                "CharacterDetail": {
                    "type": "object",
                    "description": "A character and the media item they appear in.",
                    "required": ["id", "name", "media"],
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "media": {"$ref": "#/components/schemas/Media"},
                        "quote_count": {
                            "type": "integer",
                            "description": "Number of quotes by this character. Only on the detail endpoint.",
                        },
                    },
                    "example": EXAMPLE_CHARACTER,
                },
                "CharacterPage": {
                    "type": "object",
                    "required": ["count", "next", "previous", "results"],
                    "properties": {
                        "count": {"type": "integer"},
                        "next": {"type": ["string", "null"]},
                        "previous": {"type": ["string", "null"]},
                        "results": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/CharacterDetail"},
                        },
                    },
                },
                "MediaPage": {
                    "type": "object",
                    "required": ["count", "next", "previous", "results"],
                    "properties": {
                        "count": {"type": "integer"},
                        "next": {"type": ["string", "null"]},
                        "previous": {"type": ["string", "null"]},
                        "results": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Media"},
                        },
                    },
                },
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {
                            "type": "object",
                            "required": ["code", "message"],
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Stable, machine-readable error code.",
                                },
                                "message": {
                                    "type": "string",
                                    "description": "Human-readable explanation.",
                                },
                            },
                        }
                    },
                },
            },
            "parameters": {
                "page": _query_param(
                    "page",
                    "Page number, starting at 1. Must not exceed the last page.",
                    {"type": "integer", "minimum": 1, "default": 1},
                ),
                "page_size": _query_param(
                    "page_size",
                    f"Items per page. Values above {MAX_PAGE_SIZE} are reduced to {MAX_PAGE_SIZE}.",
                    {
                        "type": "integer",
                        "minimum": 1,
                        "default": DEFAULT_PAGE_SIZE,
                    },
                ),
                "search": _query_param(
                    "search",
                    "Case-insensitive search for this text anywhere in the quote text.",
                    {"type": "string"},
                    "why so serious",
                ),
                "media_search": _query_param(
                    "search",
                    "Case-insensitive partial match on the title.",
                    {"type": "string"},
                    "dark knight",
                ),
                "media": _query_param(
                    "media",
                    "Case-insensitive partial match on the movie or show title "
                    "(`dark knight` matches \"The Dark Knight\").",
                    {"type": "string"},
                    "dark knight",
                ),
                "character": _query_param(
                    "character",
                    "Case-insensitive partial match on the character name.",
                    {"type": "string"},
                    "joker",
                ),
                "year": _query_param(
                    "year",
                    "Exact release year of the movie or show. Must be a positive integer.",
                    {"type": "integer", "minimum": 1},
                    2008,
                ),
                "language": _query_param(
                    "language",
                    "ISO 639 language code of the quote, matched case-insensitively "
                    "(e.g. `en`, `pt-BR`). Invalid codes return `400`.",
                    {"type": "string"},
                    "en",
                ),
                "tag": _query_param(
                    "tag",
                    "Return quotes that have this tag. Case-insensitive match on one tag "
                    "(tags are stored in lowercase).",
                    {"type": "string"},
                    "classic",
                ),
                "media_id": _query_param(
                    "media_id",
                    "Exact `id` of the movie or show. Must be a positive integer. "
                    "Can be combined with `media` and every other filter.",
                    {"type": "integer", "minimum": 1},
                    1,
                ),
                "character_search": _query_param(
                    "search",
                    "Case-insensitive partial match on the character name.",
                    {"type": "string"},
                    "joker",
                ),
                "character_ordering": _query_param(
                    "ordering",
                    "Sort field: `id` (default) or `name`. Prefix with `-` for descending "
                    "(e.g. `-name`). `id` is always the final tie-breaker. "
                    "Unknown values return `400`.",
                    {"type": "string", "enum": ["id", "name", "-id", "-name"]},
                    "name",
                ),
                "ordering": _query_param(
                    "ordering",
                    "Sort field: `id` (default), `title` or `year`. Prefix with `-` for "
                    "descending (e.g. `-year`). `id` is always the final tie-breaker. "
                    "Unknown values return `400`. Not applicable to `/quotes/random/`.",
                    {"type": "string", "enum": ["id", "title", "year", "-id", "-title", "-year"]},
                    "-year",
                ),
            },
            "responses": {
                "BadRequest": _error_response(
                    "A query parameter is invalid.",
                    [
                        ("invalid_parameters", "'page' must be a positive integer."),
                    ],
                ),
                "Unauthorized": _error_response(
                    "The API key is missing or not recognised.",
                    [
                        ("missing_api_key", "An API key is required."),
                        ("invalid_api_key", "The provided API key is invalid."),
                    ],
                ),
                "Forbidden": _error_response(
                    "The API key exists but can no longer be used.",
                    [
                        ("revoked_api_key", "This API key has been revoked."),
                        ("expired_api_key", "This API key has expired."),
                    ],
                ),
                "NotFound": _error_response(
                    "The requested resource does not exist.",
                    [("resource_not_found", "The requested resource does not exist.")],
                ),
                "MethodNotAllowed": _error_response(
                    "The API is read-only; only GET and HEAD are allowed.",
                    [("method_not_allowed", "This endpoint is read-only.")],
                ),
                "InternalError": _error_response(
                    "An unexpected server error occurred.",
                    [("internal_error", "An unexpected error occurred.")],
                ),
                "RateLimited": {
                    **_error_response(
                        "The key exceeded its per-minute or per-day rate limit.",
                        [
                            (
                                "rate_limit_exceeded",
                                "Rate limit exceeded. Try again later.",
                            )
                        ],
                    ),
                    "headers": {
                        "Retry-After": {
                            "description": "Seconds until the exhausted window resets.",
                            "schema": {"type": "integer", "minimum": 1},
                        },
                        **RATE_LIMIT_HEADERS,
                    },
                },
            },
            "headers": {
                "X-RateLimit-Limit": {
                    "description": "Requests allowed per minute for this key.",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Remaining": {
                    "description": "Requests left in the current minute (never negative).",
                    "schema": {"type": "integer", "minimum": 0},
                },
                "X-RateLimit-Reset": {
                    "description": "Unix timestamp when the current minute window resets.",
                    "schema": {"type": "integer"},
                },
            },
        },
    }
