# Movie Show Quotes

An API for retrieving quotes from various movies and shows.

## API

Full documentation:

- Interactive docs (Swagger UI): `/api/v1/docs/`
- OpenAPI 3.1 description: `/api/v1/openapi.json`

Both are public. Every data endpoint requires an API key.

### Quick start

1. Sign up, then create your API key at `/profile/api-keys/`. The full key is
   shown once.
2. Send the key in the `X-API-Key` header (or `Authorization: Api-Key <key>`):

```sh
curl -H "X-API-Key: <your-key>" https://<host>/api/v1/quotes/random/
```

```json
{
  "id": 123,
  "text": "Why so serious?",
  "language": "en",
  "tags": ["villain", "classic"],
  "character": {"id": 10, "name": "The Joker"},
  "media": {"id": 5, "title": "The Dark Knight", "media_type": "MOVIE", "release_year": 2008}
}
```

### Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/v1/quotes/` | Paginated list. Supports `page`, `page_size`, `search`, `media`, `character`, `year`, `language`, `tag` |
| `GET /api/v1/quotes/random/` | One random quote |
| `GET /api/v1/quotes/<id>/` | One quote by ID |

Errors always look like
`{"error": {"code": "invalid_api_key", "message": "..."}}`. See the docs for
every code and status.

The spec lives in `quotes/openapi.py`. Update it whenever an endpoint changes.
The tests fail if a `/api/v1/` route isn't documented.

## Homepage

The React/TypeScript homepage is served at `/`. The former `/homepage` URL
redirects to `/`.

The frontend source is in `frontend/`. It is built with Vite into Django's
`quotes/static/quotes/homepage/` directory, where Django serves the compiled
JavaScript and CSS.

### Build the frontend

Install Node.js and npm, then run:

```sh
npm --prefix frontend install
npm --prefix frontend run build
```

Live editing
```sh
npm --prefix frontend run dev
```

After building, start Django as usual and open `/`. Rebuild the frontend
after changing files under `frontend/src/`. The deployment script builds the
frontend before running Django's `collectstatic`, so Node.js and npm must also be
installed on the deployment host.

### Seed data

Deployment loads `quotes/fixtures/quotes.json` after migrations only when the
Media, Character, and Quote tables are all empty. If any contain data, the seed
is skipped to avoid overwriting existing records. Run
`python manage.py seed_quotes` to apply the same check manually. Fixture timestamps represent
when the seed dataset was prepared, rather than when it was loaded.

## User signup

The React signup page is available at `/signup/`. It submits to the Django
signup API and uses the CSRF token endpoint automatically.
