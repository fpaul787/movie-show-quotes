from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .auth import api_key_required
from .models import APIKey, Quote


def _key_payload(key, raw_key=None):
    payload = {
        "name": key.name,
        "prefix": key.prefix,
        "is_active": key.is_active,
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
            key = APIKey(name=f"{request.user.username} key", owner=request.user)
            raw_key = key.set_new_key()
            key.save()
        return JsonResponse({"api_key": _key_payload(key, raw_key)}, status=201)

    key = APIKey.objects.filter(owner=request.user).order_by("created_at").first()
    return JsonResponse({"api_key": _key_payload(key) if key else None})


def react_homepage(request):
    username = request.user.username if request.user.is_authenticated else ""
    return render(request, "quotes/homepage.html", {"username": username})


@api_key_required
def random_quote(request):
    quote = Quote.objects.order_by("?").first()
    if quote is None:
        return JsonResponse({"error": "No quotes available"}, status=404)
    return JsonResponse(
        {
            "text": quote.text,
            "year": quote.year,
            "title": quote.title,
            "character": quote.character,
            "source": quote.source,
            "language": quote.language,
            "tags": quote.tags,
            "created_at": quote.created_at.isoformat(),
        }
    )
