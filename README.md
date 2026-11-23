# Movie Show Quotes

A REST API for retrieving quotes from movies and TV shows, built with Django.
Live at **https://api.movie-quotes-api.com/**.

## What it supports

- List quotes with pagination and ordering
- Get a random quote or a quote by ID
- Filter by search text, media (title or ID), character, year, language and tag
- API key authentication (`X-API-Key` header or `Authorization: Api-Key <key>`)
- User signup and self-service API key management
- Consistent JSON error responses

## Documentation

Endpoint details are documented with OpenAPI:

- Interactive docs (Swagger UI): https://api.movie-quotes-api.com/api/v1/docs/
- OpenAPI 3.1 spec: https://api.movie-quotes-api.com/api/v1/openapi.json

The spec lives in `quotes/openapi.py`. Update it whenever an endpoint changes;
tests fail if a `/api/v1/` route isn't documented.

## Quick start

1. Sign up at https://api.movie-quotes-api.com/signup/, then create an API key
   at `/profile/api-keys/`. The full key is shown once.
2. Make a request:

```sh
curl -H "X-API-Key: <your-key>" https://api.movie-quotes-api.com/api/v1/quotes/random/
```

## Development

```sh
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_quotes   # loads fixtures only if the tables are empty
python manage.py runserver
```

The React/TypeScript frontend (homepage and signup) lives in `frontend/` and is
built with Vite into `quotes/static/quotes/homepage/`:

```sh
npm --prefix frontend install
npm --prefix frontend run build   # or `run dev` for live editing
```

Run tests with `python manage.py test`.
