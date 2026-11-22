from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from .. import ratelimit
from ..models import APIKey, APIUsage
from .helpers import DATA_URLS, LIST_URL, RANDOM_URL

NOW = datetime(2030, 5, 17, 12, 30, 15, tzinfo=dt_timezone.utc)
MINUTE_START = NOW.replace(second=0)
DAY_START = NOW.replace(hour=0, minute=0, second=0)


def make_key(name="test", **fields):
    key = APIKey(name=name, **fields)
    raw_key = key.set_new_key()
    key.save()
    return key, raw_key


@override_settings(API_RATE_LIMIT_PER_MINUTE=3, API_RATE_LIMIT_PER_DAY=100)
class RateLimitTests(TestCase):
    def setUp(self):
        self.key, self.raw_key = make_key()
        self.headers = {"X-API-Key": self.raw_key}
        patcher = patch("django.utils.timezone.now", return_value=NOW)
        self.now = patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, url=RANDOM_URL, headers=None):
        return self.client.get(url, headers=headers or self.headers)

    def usage(self, window):
        return APIUsage.objects.get(api_key=self.key, window=window).count

    def test_requests_under_the_limit_include_headers(self):
        expected_reset = str(int((MINUTE_START + timedelta(minutes=1)).timestamp()))
        for remaining in ("2", "1", "0"):
            response = self.get()
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response["X-RateLimit-Limit"], "3")
            self.assertEqual(response["X-RateLimit-Remaining"], remaining)
            self.assertEqual(response["X-RateLimit-Reset"], expected_reset)
            self.assertNotIn("Retry-After", response)

    def test_exceeding_the_minute_limit_returns_429(self):
        for _ in range(3):
            self.get()
        response = self.get()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Rate limit exceeded. Try again later.",
                }
            },
        )
        self.assertEqual(response["Retry-After"], "45")
        self.assertEqual(response["X-RateLimit-Limit"], "3")
        self.assertEqual(response["X-RateLimit-Remaining"], "0")

    def test_rejected_requests_still_count(self):
        for _ in range(6):
            self.get()
        self.assertEqual(self.usage("MINUTE"), 6)
        self.assertEqual(self.get().status_code, 429)
        self.assertEqual(self.usage("MINUTE"), 7)

    def test_minute_counter_resets_when_the_window_changes(self):
        for _ in range(4):
            self.get()
        self.assertEqual(self.get().status_code, 429)

        self.now.return_value = NOW + timedelta(minutes=1)
        response = self.get()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["X-RateLimit-Remaining"], "2")

    @override_settings(API_RATE_LIMIT_PER_MINUTE=100, API_RATE_LIMIT_PER_DAY=2)
    def test_daily_limit_is_enforced_independently(self):
        self.assertEqual(self.get().status_code, 404)
        self.assertEqual(self.get().status_code, 404)
        response = self.get()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["X-RateLimit-Remaining"], "97")
        seconds_to_reset = int(
            (DAY_START + timedelta(days=1) - NOW).total_seconds()
        )
        self.assertEqual(response["Retry-After"], str(seconds_to_reset))

        # A new minute does not lift the daily limit; a new day does.
        self.now.return_value = NOW + timedelta(minutes=5)
        self.assertEqual(self.get().status_code, 429)
        self.now.return_value = NOW + timedelta(days=1)
        self.assertEqual(self.get().status_code, 404)

    @override_settings(API_RATE_LIMIT_PER_MINUTE=1, API_RATE_LIMIT_PER_DAY=1)
    def test_retry_after_uses_the_daily_reset_when_both_are_exhausted(self):
        self.get()
        response = self.get()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response["Retry-After"],
            str(int((DAY_START + timedelta(days=1) - NOW).total_seconds())),
        )

    def test_counters_are_separate_per_key(self):
        other, other_raw = make_key("other")
        for _ in range(4):
            self.get()
        self.assertEqual(self.get().status_code, 429)
        response = self.get(headers={"X-API-Key": other_raw})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["X-RateLimit-Remaining"], "2")

    def test_unauthenticated_and_unusable_keys_are_not_counted(self):
        self.client.get(RANDOM_URL)
        self.client.get(RANDOM_URL, headers={"X-API-Key": "bad.key"})
        revoked, revoked_raw = make_key("revoked", is_active=False)
        expired, expired_raw = make_key(
            "expired", expires_at=NOW - timedelta(days=1)
        )
        for raw in (revoked_raw, expired_raw):
            response = self.client.get(RANDOM_URL, headers={"X-API-Key": raw})
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("X-RateLimit-Limit", response)
        self.assertFalse(APIUsage.objects.exists())

    def test_wrong_method_counts_and_includes_headers(self):
        response = self.client.post(RANDOM_URL, headers=self.headers)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["X-RateLimit-Remaining"], "2")
        self.assertEqual(self.usage("MINUTE"), 1)

    def test_limit_of_zero_disables_limiting(self):
        with override_settings(API_RATE_LIMIT_PER_MINUTE=0, API_RATE_LIMIT_PER_DAY=0):
            for _ in range(10):
                response = self.get()
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("X-RateLimit-Limit", response)
        self.assertFalse(APIUsage.objects.exists())

    def test_disabling_one_window_keeps_the_other(self):
        with override_settings(API_RATE_LIMIT_PER_MINUTE=-1, API_RATE_LIMIT_PER_DAY=1):
            self.assertEqual(self.get().status_code, 404)
            self.assertEqual(self.get().status_code, 429)
        self.assertEqual(
            list(APIUsage.objects.values_list("window", flat=True)), ["DAY"]
        )

    def test_documentation_endpoints_are_not_limited(self):
        for url in ("/api/v1/docs/", "/api/v1/openapi.json"):
            for _ in range(5):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-RateLimit-Limit", response)
        self.assertFalse(APIUsage.objects.exists())

    def test_every_data_endpoint_is_rate_limited(self):
        for url in DATA_URLS:
            with self.subTest(url=url):
                APIUsage.objects.all().delete()
                for _ in range(3):
                    self.assertNotEqual(self.get(url).status_code, 429)
                self.assertEqual(self.get(url).status_code, 429)

    def test_rate_limit_failure_returns_json_500_without_internals(self):
        with patch(
            "quotes.ratelimit._increment", side_effect=RuntimeError("secret")
        ), self.assertLogs("quotes.auth", level="ERROR"):
            response = self.get()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "internal_error")
        self.assertNotIn("secret", response.content.decode())

    def test_increment_is_a_single_statement_per_request(self):
        self.get()  # warm up
        with self.assertNumQueries(4):  # key lookup, one upsert, last_used, view count
            self.get()

    def test_counts_are_stored_per_window(self):
        self.get()
        self.get()
        usage = {u.window: u for u in APIUsage.objects.filter(api_key=self.key)}
        self.assertEqual(usage["MINUTE"].window_start, MINUTE_START)
        self.assertEqual(usage["DAY"].window_start, DAY_START)
        self.assertEqual(usage["MINUTE"].count, 2)
        self.assertEqual(usage["DAY"].count, 2)

    def test_listing_endpoint_returns_headers(self):
        response = self.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-RateLimit-Remaining"], "2")


class AtomicIncrementTests(TransactionTestCase):
    def test_concurrent_increments_are_not_lost(self):
        key, _ = make_key()
        windows = [("MINUTE", MINUTE_START), ("DAY", DAY_START)]
        threads, per_thread = 8, 10

        def work():
            try:
                for _ in range(per_thread):
                    ratelimit._increment(key.pk, windows)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=threads) as pool:
            for future in [pool.submit(work) for _ in range(threads)]:
                future.result()

        counts = dict(APIUsage.objects.filter(api_key=key).values_list("window", "count"))
        self.assertEqual(counts, {"MINUTE": 80, "DAY": 80})


class LastUsedTests(TestCase):
    def setUp(self):
        self.key, self.raw_key = make_key()
        self.headers = {"X-API-Key": self.raw_key}

    def last_used(self):
        self.key.refresh_from_db()
        return self.key.last_used_at

    def test_written_on_first_use_and_not_rewritten_within_a_minute(self):
        self.assertIsNone(self.last_used())
        with patch("django.utils.timezone.now", return_value=NOW):
            self.client.get(RANDOM_URL, headers=self.headers)
        self.assertEqual(self.last_used(), NOW)

        with patch(
            "django.utils.timezone.now", return_value=NOW + timedelta(seconds=59)
        ):
            self.client.get(RANDOM_URL, headers=self.headers)
        self.assertEqual(self.last_used(), NOW)

    def test_rewritten_once_older_than_a_minute(self):
        later = NOW + timedelta(seconds=61)
        with patch("django.utils.timezone.now", return_value=NOW):
            self.client.get(RANDOM_URL, headers=self.headers)
        with patch("django.utils.timezone.now", return_value=later):
            self.client.get(RANDOM_URL, headers=self.headers)
        self.assertEqual(self.last_used(), later)


class PruneAPIUsageTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("prune_api_usage", *args, stdout=out)
        return out.getvalue()

    def test_deletes_only_old_windows_and_is_repeatable(self):
        key, _ = make_key()
        now = timezone.now()
        old = APIUsage.objects.create(
            api_key=key, window="MINUTE", window_start=now - timedelta(days=3), count=1
        )
        APIUsage.objects.create(
            api_key=key, window="DAY", window_start=now - timedelta(days=1), count=1
        )
        APIUsage.objects.create(
            api_key=key, window="MINUTE", window_start=now + timedelta(hours=1), count=1
        )

        self.run_command()
        self.assertFalse(APIUsage.objects.filter(pk=old.pk).exists())
        self.assertEqual(APIUsage.objects.count(), 2)

        self.run_command()
        self.assertEqual(APIUsage.objects.count(), 2)

        self.run_command("--days", "0")
        self.assertEqual(APIUsage.objects.count(), 1)

    def test_usage_is_deleted_with_its_key(self):
        key, _ = make_key()
        APIUsage.objects.create(
            api_key=key, window="MINUTE", window_start=MINUTE_START, count=1
        )
        key.delete()
        self.assertFalse(APIUsage.objects.exists())

    def test_unique_constraint_on_key_window_and_start(self):
        from django.db import IntegrityError, transaction

        key, _ = make_key()
        APIUsage.objects.create(
            api_key=key, window="MINUTE", window_start=MINUTE_START, count=1
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            APIUsage.objects.create(
                api_key=key, window="MINUTE", window_start=MINUTE_START, count=1
            )
