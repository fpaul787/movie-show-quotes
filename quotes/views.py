from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from .auth import api_key_required
from .errors import api_error
from .models import LANGUAGE_CODE_VALIDATOR, APIKey, Quote


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


def _filter_quotes(params):
    """Apply the optional filters and search; blank values are ignored."""
    quotes = _quotes()
    value = lambda name: params.get(name, "").strip()  # noqa: E731

    if value("media"):
        quotes = quotes.filter(media__title__icontains=value("media"))
    if value("character"):
        quotes = quotes.filter(character__name__icontains=value("character"))
    if value("year"):
        year = _positive_int(params, "year", None)
        quotes = quotes.filter(media__release_year=year)
    if value("language"):
        try:
            LANGUAGE_CODE_VALIDATOR(value("language"))
        except ValidationError:
            raise ValueError("'language' must be a valid language code, e.g. 'en'.")
        quotes = quotes.filter(language__iexact=value("language"))
    if value("tag"):
        quotes = quotes.filter(tags__contains=[value("tag")])
    if value("search"):
        quotes = quotes.filter(text__icontains=value("search"))
    return quotes.order_by("id")


@api_key_required
@require_GET
def quote_list(request):
    """Served at /api/v1/quotes/."""
    try:
        page_number = _positive_int(request.GET, "page", 1)
        page_size = min(
            _positive_int(request.GET, "page_size", DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE
        )
        quotes = _filter_quotes(request.GET)
    except ValueError as exc:
        return _invalid(str(exc))

    paginator = Paginator(quotes, page_size)
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
            "results": [serialize_quote(q) for q in page.object_list],
        }
    )


@api_key_required
@require_GET
def quote_detail(request, pk):
    """Served at /api/v1/quotes/<pk>/."""
    quote = _quotes().filter(pk=pk).first()
    if quote is None:
        return api_error("resource_not_found", "The requested quote does not exist.", 404)
    return JsonResponse(serialize_quote(quote))


@api_key_required
def random_quote(request):
    """Served at /api/v1/quotes/random/."""
    quote = _quotes().order_by("?").first()
    if quote is None:
        return api_error("no_quotes_available", "No quotes available.", 404)
    return JsonResponse(serialize_quote(quote))
