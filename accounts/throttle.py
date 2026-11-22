from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import connection
from django.db.models import F
from django.utils import timezone

from .models import LoginAttempt

IDENTIFIER_MAX_LENGTH = 150


def client_ip(request):
    # X-Forwarded-For is client-controlled, so it is intentionally ignored.
    return request.META.get("REMOTE_ADDR", "")[:IDENTIFIER_MAX_LENGTH]


def normalize_username(username):
    return username.strip().lower()[:IDENTIFIER_MAX_LENGTH]


def _window_start(now):
    size = settings.LOGIN_THROTTLE_WINDOW_SECONDS
    seconds = int(now.timestamp()) // size * size
    return datetime.fromtimestamp(seconds, dt_timezone.utc)


def _thresholds(username, ip):
    return (
        (LoginAttempt.Scope.USERNAME, username, settings.LOGIN_MAX_FAILURES_PER_USERNAME),
        (LoginAttempt.Scope.IP, ip, settings.LOGIN_MAX_FAILURES_PER_IP),
    )


def reserve_attempt(username, ip):
    """Count this attempt for the username and IP, and return True if throttled.

    The increment and the decision are one atomic statement, so concurrent
    attempts cannot all slip under the threshold. Attempts rejected here stay
    counted. Call release_success() after a successful login so the IP counter
    keeps reflecting failures only.
    """
    if settings.LOGIN_THROTTLE_WINDOW_SECONDS <= 0:
        return False
    window_start = _window_start(timezone.now())
    table = connection.ops.quote_name(LoginAttempt._meta.db_table)
    sql = (
        f"INSERT INTO {table} (scope, identifier, window_start, count) "
        "VALUES (%s, %s, %s, 1), (%s, %s, %s, 1) "
        "ON CONFLICT (scope, identifier, window_start) "
        f"DO UPDATE SET count = {table}.count + 1 "
        "RETURNING scope, count"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            [
                LoginAttempt.Scope.USERNAME, username, window_start,
                LoginAttempt.Scope.IP, ip, window_start,
            ],
        )
        counts = dict(cursor.fetchall())
    return any(
        limit > 0 and counts[scope] > limit
        for scope, _, limit in _thresholds(username, ip)
    )


def release_success(username, ip):
    """After a successful login, clear the username counter and refund the IP."""
    if settings.LOGIN_THROTTLE_WINDOW_SECONDS <= 0:
        return
    LoginAttempt.objects.filter(
        scope=LoginAttempt.Scope.USERNAME, identifier=username
    ).delete()
    LoginAttempt.objects.filter(
        scope=LoginAttempt.Scope.IP,
        identifier=ip,
        window_start=_window_start(timezone.now()),
        count__gt=0,
    ).update(count=F("count") - 1)
