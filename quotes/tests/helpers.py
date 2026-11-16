"""Shared constants for the quotes tests."""

RANDOM_URL = "/api/v1/quotes/random/"
LIST_URL = "/api/v1/quotes/"
DETAIL_URL = "/api/v1/quotes/1/"
MOVIES_URL = "/api/v1/media/movies/"
TV_SHOWS_URL = "/api/v1/media/tv-shows/"
MEDIA_DETAIL_URL = "/api/v1/media/1/"
# Add each new data endpoint here so it is covered by the auth tests.
DATA_URLS = [
    RANDOM_URL, LIST_URL, DETAIL_URL, MOVIES_URL, TV_SHOWS_URL, MEDIA_DETAIL_URL,
]
