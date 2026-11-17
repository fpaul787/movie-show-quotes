import logging
from datetime import timedelta
from functools import wraps

from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import ratelimit
from .errors import api_error
from .models import APIKey


logger = logging.getLogger(__name__)

LAST_USED_WRITE_INTERVAL = timedelta(seconds=60)


def _record_last_used(key):
    now = timezone.now()
    APIKey.objects.filter(pk=key.pk).filter(
        Q(last_used_at__isnull=True)
        | Q(last_used_at__lt=now - LAST_USED_WRITE_INTERVAL)
    ).update(last_used_at=now)


def _extract_key(request):
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "api-key" and value:
        return value.strip()
    return request.headers.get("X-API-Key", "").strip()


def api_key_required(view):
    def authorize_and_call(request, *args, **kwargs):
        raw_key = _extract_key(request)
        if not raw_key:
            return api_error("missing_api_key", "An API key is required.", 401)
        key = APIKey.authenticate(raw_key)
        if key is None:
            return api_error("invalid_api_key", "The provided API key is invalid.", 401)
        if not key.is_usable():
            if key.is_revoked():
                return api_error("revoked_api_key", "This API key has been revoked.", 403)
            return api_error("expired_api_key", "This API key has expired.", 403)
        # Rejected (429) and wrong-method requests still count against the limits.
        usage = ratelimit.record_request(key)
        if usage.exceeded:
            response = api_error(
                "rate_limit_exceeded", "Rate limit exceeded. Try again later.", 429
            )
        elif request.method not in ("GET", "HEAD"):
            response = api_error(
                "method_not_allowed", "This endpoint is read-only.", 405
            )
            response["Allow"] = "GET, HEAD"
        else:
            _record_last_used(key)
            response = view(request, *args, **kwargs)
        return ratelimit.apply_headers(response, usage)

    @csrf_exempt
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return authorize_and_call(request, *args, **kwargs)
        except Exception:
            logger.exception("Unhandled error in API view %s", view.__name__)
            return api_error(
                "internal_error", "An unexpected error occurred.", 500
            )

    return wrapper
