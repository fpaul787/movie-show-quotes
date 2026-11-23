import random

from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from .auth import api_key_required
from .errors import api_error
from .models import LANGUAGE_CODE_VALIDATOR, APIKey, Character, Media, Quote
from .openapi import build_openapi_spec


def _key_payload(key, raw_key=None):
    payload = {
        "name": key.name,
        "prefix": key.prefix,
        "is_active": key.is_usable(),
        "created_at": key.created_at.isoformat(),
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
    }
    if raw_key is not None:
        payload["key"] = raw_key
    return payload


@require_http_methods(["GET", "POST", "DELETE"])
def api_key(request):
    """View, create, or delete the current user's API key."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    if request.method == "DELETE":
        key = APIKey.objects.filter(owner=request.user).order_by("created_at").first()
        if key is None:
            return JsonResponse({"error": "API key not found"}, status=404)
        key.delete()
        return JsonResponse({"deleted": True})

    if request.method == "POST":
        with transaction.atomic():
            # Lock the user row so concurrent requests can't create two keys.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if APIKey.objects.filter(owner=request.user).exists():
                return JsonResponse({"error": "API key already exists"}, status=409)
            if APIKey.objects.count() >= settings.MAX_API_KEYS:
                return JsonResponse({"error": "Limit reached"}, status=403)
            suffix = " key"
            max_username_length = APIKey._meta.get_field("name").max_length - len(suffix)
            key = APIKey(
                name=f"{request.user.username[:max_username_length]}{suffix}",
                owner=request.user,
            )
            raw_key = key.save_with_new_key()
        return JsonResponse({"api_key": _key_payload(key, raw_key)}, status=201)

    key = APIKey.objects.filter(owner=request.user).order_by("created_at").first()
    return JsonResponse({"api_key": _key_payload(key) if key else None})


def react_homepage(request):
    username = request.user.username if request.user.is_authenticated else ""
    return render(request, "quotes/homepage.html", {"username": username})


def api_not_found(request, *args, **kwargs):
    return api_error("resource_not_found", "The requested resource does not exist.", 404)


@require_GET
def openapi_schema(request):
    """Public OpenAPI description of the v1 API, served at /api/v1/openapi.json."""
    return JsonResponse(build_openapi_spec())


@require_GET
def api_docs(request):
    """Public interactive API documentation, served at /api/v1/docs/."""
    return render(request, "quotes/api_docs.html")


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _quotes():
    return Quote.objects.select_related("media", "character")


def serialize_quote(quote):
    character = quote.character
    media = quote.media
    return {
        "id": quote.id,
        "text": quote.text,
        "language": quote.language,
        "tags": quote.tags,
        "character": {"id": character.id, "name": character.name} if character else None,
        "media": {
            "id": media.id,
            "title": media.title,
            "media_type": media.media_type,
            "release_year": media.release_year,
        },
    }


def _invalid(message):
    return api_error("invalid_parameters", message, 400)


def _positive_int(params, name, default):
    raw = params.get(name, "").strip()
    if not raw:
        return default
    if not raw.isascii() or not raw.isdigit() or int(raw) < 1:
        raise ValueError(f"'{name}' must be a positive integer.")
    return int(raw)


QUOTE_ORDERING = {"id": "id", "title": "media__title", "year": "media__release_year"}
MEDIA_ORDERING = {"id": "id", "title": "title", "year": "release_year"}
CHARACTER_ORDERING = {"id": "id", "name": "name"}


def _apply_ordering(queryset, params, allowed):
    """Order by a friendly `ordering` value mapped through an explicit allowlist."""
    raw = params.get("ordering", "").strip()
    descending = raw.startswith("-")
    name = raw[1:] if descending else raw
    if not raw:
        name = "id"
    if name not in allowed:
        raise ValueError(
            f"'ordering' must be one of: {', '.join(allowed)} "
            "(prefix with '-' for descending)."
        )
    prefix = "-" if descending else ""
    fields = [f"{prefix}{allowed[name]}"]
    if name != "id":
        fields.append(f"{prefix}id")
    return queryset.order_by(*fields)


def _filter_quotes(params):
    """Apply the optional filters and search; blank values are ignored."""
    quotes = _quotes()
    value = lambda name: params.get(name, "").strip()  # noqa: E731

    if value("media"):
        quotes = quotes.filter(media__title__icontains=value("media"))
    if value("media_id"):
        quotes = quotes.filter(media_id=_positive_int(params, "media_id", None))
    if value("character"):
        quotes = quotes.filter(character__name__icontains=value("character"))
    if value("year"):
        year = _positive_int(params, "year", None)
        quotes = quotes.filter(media__release_year=year)
    if value("language"):
        language = value("language").lower()
        try:
            LANGUAGE_CODE_VALIDATOR(language)
        except ValidationError:
            raise ValueError("'language' must be a valid language code, e.g. 'en'.")
        quotes = quotes.filter(language__iexact=language)
    if value("tag"):
        quotes = quotes.filter(tags__contains=[value("tag").lower()])
    if value("search"):
        quotes = quotes.filter(text__icontains=value("search"))
    return quotes


@api_key_required
def quote_list(request):
    """Served at /api/v1/quotes/."""
    return _paginated_response(
        request,
        lambda params: _apply_ordering(_filter_quotes(params), params, QUOTE_ORDERING),
        serialize_quote,
    )


def _paginated_response(request, build_queryset, serialize):
    try:
        page_number = _positive_int(request.GET, "page", 1)
        page_size = min(
            _positive_int(request.GET, "page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE
        )
        queryset = build_queryset(request.GET)
    except ValueError as exc:
        return _invalid(str(exc))

    paginator = Paginator(queryset, page_size)
    if page_number > paginator.num_pages:
        return _invalid(f"'page' must be between 1 and {paginator.num_pages}.")
    page = paginator.page(page_number)

    def page_url(number):
        query = request.GET.copy()
        query["page"] = number
        return f"{request.path}?{query.urlencode()}"

    return JsonResponse(
        {
            "count": paginator.count,
            "next": page_url(page.next_page_number()) if page.has_next() else None,
            "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
            "results": [serialize(item) for item in page.object_list],
        }
    )


def serialize_media(media, include_characters=False):
    data = {
        "id": media.id,
        "title": media.title,
        "media_type": media.media_type,
        "release_year": media.release_year,
    }
    if include_characters:
        data["characters"] = [
            {"id": c.id, "name": c.name}
            for c in sorted(media.characters.all(), key=lambda c: (c.name, c.id))
        ]
    return data


def _filter_media(params, media_type):
    media = Media.objects.filter(media_type=media_type)
    if params.get("search", "").strip():
        media = media.filter(title__icontains=params["search"].strip())
    if params.get("year", "").strip():
        media = media.filter(release_year=_positive_int(params, "year", None))
    return _apply_ordering(media, params, MEDIA_ORDERING)


@api_key_required
def movie_list(request):
    """Served at /api/v1/media/movies/."""
    return _paginated_response(
        request,
        lambda params: _filter_media(params, Media.MediaType.MOVIE),
        serialize_media,
    )


@api_key_required
def tv_show_list(request):
    """Served at /api/v1/media/tv-shows/."""
    return _paginated_response(
        request,
        lambda params: _filter_media(params, Media.MediaType.TV_SHOW),
        serialize_media,
    )


@api_key_required
def media_detail(request, pk):
    """Served at /api/v1/media/<pk>/."""
    media = Media.objects.prefetch_related("characters").filter(pk=pk).first()
    if media is None:
        return api_error("resource_not_found", "The requested media does not exist.", 404)
    return JsonResponse(serialize_media(media, include_characters=True))


def serialize_character(character, include_quote_count=False):
    data = {
        "id": character.id,
        "name": character.name,
        "media": serialize_media(character.media),
    }
    if include_quote_count:
        data["quote_count"] = character.quote_count
    return data


def _filter_characters(params):
    characters = Character.objects.select_related("media")
    if params.get("search", "").strip():
        characters = characters.filter(name__icontains=params["search"].strip())
    if params.get("media_id", "").strip():
        characters = characters.filter(media_id=_positive_int(params, "media_id", None))
    return _apply_ordering(characters, params, CHARACTER_ORDERING)


@api_key_required
def character_list(request):
    """Served at /api/v1/characters/."""
    return _paginated_response(request, _filter_characters, serialize_character)


@api_key_required
def character_detail(request, pk):
    """Served at /api/v1/characters/<pk>/."""
    character = (
        Character.objects.select_related("media")
        .annotate(quote_count=Count("quotes"))
        .filter(pk=pk)
        .first()
    )
    if character is None:
        return api_error("resource_not_found", "The requested character does not exist.", 404)
    return JsonResponse(serialize_character(character, include_quote_count=True))


@api_key_required
def media_quote_list(request, pk):
    """Served at /api/v1/media/<pk>/quotes/."""
    if not Media.objects.filter(pk=pk).exists():
        return api_error("resource_not_found", "The requested media does not exist.", 404)

    def build_queryset(params):
        # The media is fixed by the URL, so these filters don't apply.
        params = params.copy()
        params.pop("media", None)
        params.pop("media_id", None)
        quotes = _filter_quotes(params).filter(media_id=pk)
        return _apply_ordering(quotes, params, QUOTE_ORDERING)

    return _paginated_response(request, build_queryset, serialize_quote)


@api_key_required
def quote_detail(request, pk):
    """Served at /api/v1/quotes/<pk>/."""
    quote = _quotes().filter(pk=pk).first()
    if quote is None:
        return api_error("resource_not_found", "The requested quote does not exist.", 404)
    return JsonResponse(serialize_quote(quote))


@api_key_required
def random_quote(request):
    """Served at /api/v1/quotes/random/."""
    # A random offset over the primary-key order avoids sorting the whole table.
    try:
        quotes = _filter_quotes(request.GET).order_by("id")
    except ValueError as exc:
        return _invalid(str(exc))
    # Retry in case quotes are deleted between the count and the offset lookup.
    for _ in range(3):
        count = quotes.count()
        if count == 0:
            break
        quote = quotes[random.randrange(count):][:1]
        quote = next(iter(quote), None)
        if quote is not None:
            return JsonResponse(serialize_quote(quote))
    return api_error("no_quotes_available", "No quotes available.", 404)
