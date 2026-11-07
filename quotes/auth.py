from functools import wraps

from django.http import JsonResponse
from django.utils import timezone

from .models import APIKey


def _extract_key(request):
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "api-key" and value:
        return value.strip()
    return request.headers.get("X-API-Key", "").strip()


def api_key_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        key = APIKey.authenticate(_extract_key(request))
        if key is None:
            return JsonResponse({"error": "Invalid or missing API key"}, status=401)
        if not key.is_usable():
            return JsonResponse({"error": "API key is revoked or expired"}, status=403)
        APIKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return view(request, *args, **kwargs)

    return wrapper
