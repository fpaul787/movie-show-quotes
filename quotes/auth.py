from functools import wraps

from django.utils import timezone

from .errors import api_error
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
        raw_key = _extract_key(request)
        if not raw_key:
            return api_error("missing_api_key", "An API key is required.", 401)
        key = APIKey.authenticate(raw_key)
        if key is None:
            return api_error("invalid_api_key", "The provided API key is invalid.", 401)
        if not key.is_usable():
            if not key.is_active:
                return api_error("revoked_api_key", "This API key has been revoked.", 403)
            return api_error("expired_api_key", "This API key has expired.", 403)
        APIKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        return view(request, *args, **kwargs)

    return wrapper
