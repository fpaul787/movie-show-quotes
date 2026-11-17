import math
from dataclasses import dataclass
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import connection
from django.utils import timezone

from .models import APIUsage


@dataclass
class RateLimitState:
    """Outcome of counting one request."""

    minute_limit: int = 0
    minute_remaining: int = 0
    minute_reset: int = 0  # Unix timestamp
    retry_after: int = 0  # seconds; > 0 only when a limit was exceeded

    @property
    def exceeded(self):
        return self.retry_after > 0

    @property
    def has_minute_limit(self):
        return self.minute_limit > 0


def _increment(api_key_id, windows):
    """Atomically count one request in each window with a single statement.

    `windows` is a list of (window, window_start). Returns {window: new_count}.
    """
    quote = connection.ops.quote_name
    table = quote(APIUsage._meta.db_table)
    rows = ", ".join(["(%s, %s, %s, 1)"] * len(windows))
    sql = (
        f"INSERT INTO {table} (api_key_id, {quote('window')}, window_start, count) "
        f"VALUES {rows} "
        f"ON CONFLICT (api_key_id, {quote('window')}, window_start) "
        f"DO UPDATE SET count = {table}.count + 1 "
        f"RETURNING {quote('window')}, count"
    )
    params = []
    for window, window_start in windows:
        params.extend([api_key_id, window, window_start])
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return dict(cursor.fetchall())


def record_request(api_key, now=None):
    """Count a request against the key's enabled windows and report the result."""
    now = (now or timezone.now()).astimezone(dt_timezone.utc)
    minute_start = now.replace(second=0, microsecond=0)
    day_start = minute_start.replace(hour=0, minute=0)

    limits = {}
    if settings.API_RATE_LIMIT_PER_MINUTE > 0:
        limits[APIUsage.Window.MINUTE] = (
            settings.API_RATE_LIMIT_PER_MINUTE,
            minute_start,
            minute_start + timedelta(minutes=1),
        )
    if settings.API_RATE_LIMIT_PER_DAY > 0:
        limits[APIUsage.Window.DAY] = (
            settings.API_RATE_LIMIT_PER_DAY,
            day_start,
            day_start + timedelta(days=1),
        )
    if not limits:
        return RateLimitState()

    counts = _increment(
        api_key.pk, [(window, start) for window, (_, start, _) in limits.items()]
    )

    state = RateLimitState()
    for window, (limit, _, reset) in limits.items():
        count = counts[window]
        if window == APIUsage.Window.MINUTE:
            state.minute_limit = limit
            state.minute_remaining = max(0, limit - count)
            state.minute_reset = int(reset.timestamp())
        if count > limit:
            wait = max(1, math.ceil((reset - now).total_seconds()))
            state.retry_after = max(state.retry_after, wait)
    return state


def apply_headers(response, state):
    if state.has_minute_limit:
        response["X-RateLimit-Limit"] = str(state.minute_limit)
        response["X-RateLimit-Remaining"] = str(state.minute_remaining)
        response["X-RateLimit-Reset"] = str(state.minute_reset)
    if state.exceeded:
        response["Retry-After"] = str(state.retry_after)
    return response


def prune(older_than):
    """Delete usage windows that started before `older_than`."""
    deleted, _ = APIUsage.objects.filter(window_start__lt=older_than).delete()
    return deleted
