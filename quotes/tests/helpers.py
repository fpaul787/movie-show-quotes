"""Shared constants for the quotes tests."""

RANDOM_URL = "/api/v1/quotes/random/"
LIST_URL = "/api/v1/quotes/"
DETAIL_URL = "/api/v1/quotes/1/"
MOVIES_URL = "/api/v1/media/movies/"
TV_SHOWS_URL = "/api/v1/media/tv-shows/"
MEDIA_DETAIL_URL = "/api/v1/media/1/"
CHARACTERS_URL = "/api/v1/characters/"
CHARACTER_DETAIL_URL = "/api/v1/characters/1/"
MEDIA_QUOTES_URL = "/api/v1/media/1/quotes/"
# Add each new data endpoint here so it is covered by the auth tests.
DATA_URLS = [
    RANDOM_URL, LIST_URL, DETAIL_URL, MOVIES_URL, TV_SHOWS_URL, MEDIA_DETAIL_URL,
    CHARACTERS_URL, CHARACTER_DETAIL_URL, MEDIA_QUOTES_URL,
]
