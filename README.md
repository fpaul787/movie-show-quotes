# Movie Show Quotes

An API for retrieving quotes from various movies and shows.

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

## User signup

The React signup page is available at `/signup/`. It submits to the Django
signup API and uses the CSRF token endpoint automatically.
