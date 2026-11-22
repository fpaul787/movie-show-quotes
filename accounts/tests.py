from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import LoginAttempt
from quotes.models import APIKey


class UserModelTests(TestCase):
    def test_api_key_can_be_owned_by_a_user(self):
        user = get_user_model().objects.create_user(
            username="api-owner",
            password="test-password",
        )
        api_key = APIKey.objects.create(name="test", owner=user)

        self.assertEqual(api_key.owner, user)
        self.assertEqual(user.apikey_set.get(), api_key)


class SignupApiTests(TestCase):
    payload = {
        "username": "newuser",
        "email": "new@example.com",
        "password1": "a-Long-unusual-pass-123",
        "password2": "a-Long-unusual-pass-123",
    }

    def post(self, data, client=None):
        return (client or self.client).post(
            "/api/auth/signup", data=data, content_type="application/json"
        )

    def test_signup_creates_user_with_hashed_password(self):
        response = self.post(self.payload)

        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username="newuser")
        self.assertEqual(response.json(), {"id": user.pk, "username": "newuser"})
        self.assertNotEqual(user.password, self.payload["password1"])
        self.assertTrue(user.check_password(self.payload["password1"]))
        self.assertFalse(user.is_staff)

    def test_signup_validates_input(self):
        weak = {**self.payload, "password1": "12345678", "password2": "12345678"}
        response = self.post(weak)

        self.assertEqual(response.status_code, 400)
        self.assertIn("password2", response.json()["errors"])
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_duplicate_email_is_rejected_on_signup(self):
        self.post(self.payload)
        other = {**self.payload, "username": "another", "email": "NEW@example.com"}
        response = self.post(other)

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])

    def test_signup_race_on_email_returns_400_not_500(self):
        get_user_model().objects.create_user(
            username="first", email="new@example.com", password="x"
        )

        with patch("accounts.forms.email_in_use", return_value=False), patch(
            "django.db.models.Model.validate_constraints"
        ):
            response = self.post(self.payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])
        self.assertFalse(get_user_model().objects.filter(username="newuser").exists())

    def test_duplicate_username_is_rejected(self):
        self.post(self.payload)
        response = self.post(self.payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.json()["errors"])

    def test_invalid_json_returns_400(self):
        response = self.post("not json")
        self.assertEqual(response.status_code, 400)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get("/api/auth/signup").status_code, 405)

    def test_csrf_is_enforced_and_token_endpoint_works(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(self.payload, client).status_code, 403)

        token = client.get("/api/auth/csrf").json()["csrfToken"]
        response = client.post(
            "/api/auth/signup",
            data=self.payload,
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(response.status_code, 201)


class LoginApiTests(TestCase):
    username = "existing-user"
    password = "a-Long-unusual-pass-123"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username=self.username, password=self.password
        )

    def post(self, data, client=None):
        return (client or self.client).post(
            "/api/auth/login", data=data, content_type="application/json"
        )

    def test_valid_credentials_create_a_session(self):
        response = self.post(
            {"username": self.username, "password": self.password}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"id": self.user.pk, "username": self.username}
        )
        self.assertEqual(
            self.client.session["_auth_user_id"], str(self.user.pk)
        )

    def test_invalid_credentials_return_the_same_generic_error(self):
        wrong_password = self.post(
            {"username": self.username, "password": "incorrect"}
        )
        unknown_user = self.post(
            {"username": "unknown-user", "password": self.password}
        )

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_user.status_code, 401)
        self.assertEqual(
            wrong_password.json(), {"error": "Invalid username or password"}
        )
        self.assertEqual(wrong_password.json(), unknown_user.json())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()

        response = self.post(
            {"username": self.username, "password": self.password}
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_invalid_json_and_missing_credentials_return_400(self):
        malformed = self.post("not json")
        missing_password = self.post({"username": self.username})

        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json(), {"error": "Invalid JSON"})
        self.assertEqual(missing_password.status_code, 400)
        self.assertEqual(
            missing_password.json(), {"error": "Username and password are required"}
        )

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get("/api/auth/login").status_code, 405)

    def test_csrf_is_enforced_and_token_endpoint_works(self):
        client = Client(enforce_csrf_checks=True)
        payload = {"username": self.username, "password": self.password}
        self.assertEqual(self.post(payload, client).status_code, 403)

        token = client.get("/api/auth/csrf").json()["csrfToken"]
        response = client.post(
            "/api/auth/login",
            data=payload,
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"id": self.user.pk, "username": self.username}
        )
        self.assertEqual(
            client.session["_auth_user_id"], str(self.user.pk)
        )


@override_settings(
    LOGIN_MAX_FAILURES_PER_USERNAME=3,
    LOGIN_MAX_FAILURES_PER_IP=5,
    LOGIN_THROTTLE_WINDOW_SECONDS=900,
)
class LoginThrottleTests(TestCase):
    username = "Throttled-User"
    password = "a-Long-unusual-pass-123"
    throttled = {"error": "Too many login attempts. Try again later."}

    def setUp(self):
        get_user_model().objects.create_user(self.username, password=self.password)

    def attempt(self, username=None, password="wrong", ip="10.0.0.1"):
        return self.client.post(
            "/api/auth/login",
            data={"username": username or self.username, "password": password},
            content_type="application/json",
            REMOTE_ADDR=ip,
        )

    def test_username_is_locked_out_after_the_threshold(self):
        for _ in range(3):
            self.assertEqual(self.attempt().status_code, 401)

        response = self.attempt()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), self.throttled)
        # Even the correct password is rejected while locked out.
        response = self.attempt(password=self.password)
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_username_is_normalized_and_counted_across_ips(self):
        self.attempt(self.username.upper(), ip="10.0.0.1")
        self.attempt(f"  {self.username.lower()} ", ip="10.0.0.2")
        self.attempt(self.username, ip="10.0.0.3")
        self.assertEqual(self.attempt(ip="10.0.0.4").status_code, 429)

    def test_lockout_does_not_affect_other_users(self):
        get_user_model().objects.create_user("other-user", password=self.password)
        for _ in range(4):
            self.attempt()
        response = self.attempt("other-user", self.password, ip="10.0.0.2")
        self.assertEqual(response.status_code, 200)

    def test_ip_is_locked_out_across_usernames(self):
        for index in range(5):
            self.assertEqual(self.attempt(f"user-{index}").status_code, 401)
        response = self.attempt("user-new")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), self.throttled)
        self.assertEqual(self.attempt("user-new", ip="10.0.0.9").status_code, 401)

    def test_success_clears_the_username_counter_but_not_the_ip_counter(self):
        self.attempt()
        self.attempt()
        self.assertEqual(self.attempt(password=self.password).status_code, 200)
        self.assertFalse(
            LoginAttempt.objects.filter(scope="USERNAME").exists()
        )
        self.assertEqual(
            LoginAttempt.objects.get(scope="IP", identifier="10.0.0.1").count, 2
        )
        # The username has a fresh budget of three failures.
        for _ in range(3):
            self.assertEqual(self.attempt().status_code, 401)
        self.assertEqual(self.attempt().status_code, 429)

    def test_counters_reset_in_the_next_window(self):
        for _ in range(3):
            self.attempt()
        self.assertEqual(self.attempt().status_code, 429)
        later = timezone.now() + timedelta(seconds=900)
        with patch("django.utils.timezone.now", return_value=later):
            self.assertEqual(self.attempt(password=self.password).status_code, 200)

    def test_x_forwarded_for_is_ignored(self):
        for index in range(5):
            self.client.post(
                "/api/auth/login",
                data={"username": f"user-{index}", "password": "wrong"},
                content_type="application/json",
                REMOTE_ADDR="10.0.0.1",
                HTTP_X_FORWARDED_FOR=f"203.0.113.{index}",
            )
        self.assertEqual(self.attempt("user-new").status_code, 429)

    def test_invalid_requests_do_not_count(self):
        for _ in range(6):
            self.client.post(
                "/api/auth/login",
                data={"username": self.username},
                content_type="application/json",
                REMOTE_ADDR="10.0.0.1",
            )
        self.assertFalse(LoginAttempt.objects.exists())

    @override_settings(LOGIN_MAX_FAILURES_PER_USERNAME=0, LOGIN_MAX_FAILURES_PER_IP=0)
    def test_zero_thresholds_disable_throttling(self):
        for _ in range(10):
            self.assertEqual(self.attempt().status_code, 401)
        self.assertEqual(self.attempt(password=self.password).status_code, 200)

    def test_prune_removes_old_login_attempts(self):
        old = timezone.now() - timedelta(days=3)
        LoginAttempt.objects.create(
            scope="IP", identifier="10.0.0.1", window_start=old, count=1
        )
        self.attempt()
        call_command("prune_api_usage", stdout=StringIO())
        self.assertEqual(LoginAttempt.objects.filter(window_start__lt=old).count(), 0)
        self.assertEqual(LoginAttempt.objects.count(), 2)


class LoginThrottleConcurrencyTests(TransactionTestCase):
    @override_settings(
        LOGIN_MAX_FAILURES_PER_USERNAME=3,
        LOGIN_MAX_FAILURES_PER_IP=0,
        LOGIN_THROTTLE_WINDOW_SECONDS=900,
    )
    def test_parallel_attempts_cannot_exceed_the_threshold(self):
        threads = 12

        def attempt(_):
            try:
                return Client().post(
                    "/api/auth/login",
                    data={"username": "victim", "password": "wrong"},
                    content_type="application/json",
                    REMOTE_ADDR="10.0.0.1",
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=threads) as pool:
            statuses = list(pool.map(attempt, range(threads)))

        self.assertEqual(statuses.count(401), 3)
        self.assertEqual(statuses.count(429), threads - 3)


class CurrentUserApiTests(TestCase):
    def test_anonymous_request_returns_no_user(self):
        response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"user": None})

    def test_authenticated_request_returns_current_user(self):
        user = get_user_model().objects.create_user(
            username="current-user", password="a-Long-unusual-pass-123"
        )
        self.client.force_login(user)

        response = self.client.get("/api/auth/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"user": {"id": user.pk, "username": user.username}},
        )


class ProfileApiTests(TestCase):
    def test_anonymous_request_returns_401(self):
        response = self.client.get("/api/auth/profile")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Authentication required"})

    def test_returns_username_and_email(self):
        user = get_user_model().objects.create_user(
            username="profile-user", email="p@example.com", password="x"
        )
        self.client.force_login(user)

        response = self.client.get("/api/auth/profile")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"username": "profile-user", "email": "p@example.com"}
        )

    def test_missing_email_is_null(self):
        user = get_user_model().objects.create_user(username="no-email", password="x")
        self.client.force_login(user)

        response = self.client.get("/api/auth/profile")

        self.assertEqual(response.json(), {"username": "no-email", "email": None})

    def test_post_is_not_allowed(self):
        self.assertEqual(self.client.post("/api/auth/profile").status_code, 405)

    def patch(self, data, client=None):
        return (client or self.client).patch(
            "/api/auth/profile", data=data, content_type="application/json"
        )

    def login(self, email=""):
        user = get_user_model().objects.create_user(
            username="editor", email=email, password="x"
        )
        self.client.force_login(user)
        return user

    def test_patch_updates_email(self):
        user = self.login("old@example.com")

        response = self.patch({"email": "new@example.com"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"username": "editor", "email": "new@example.com"}
        )
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")

    def test_patch_can_clear_email(self):
        user = self.login("old@example.com")

        response = self.patch({"email": ""})

        self.assertEqual(response.json()["email"], None)
        user.refresh_from_db()
        self.assertEqual(user.email, "")

    def test_patch_rejects_invalid_email(self):
        user = self.login("old@example.com")

        response = self.patch({"email": "not-an-email"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")

    def test_patch_rejects_bad_json_and_missing_email(self):
        self.login()

        self.assertEqual(self.patch("not json").status_code, 400)
        self.assertEqual(self.patch({}).status_code, 400)

    def test_patch_rejects_email_used_by_another_user_case_insensitively(self):
        get_user_model().objects.create_user(
            username="other", email="Taken@Example.com", password="x"
        )
        user = self.login("old@example.com")

        response = self.patch({"email": "taken@example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")

    def test_patch_race_on_email_returns_400_not_500(self):
        get_user_model().objects.create_user(
            username="other", email="taken@example.com", password="x"
        )
        user = self.login("old@example.com")

        with patch("accounts.forms.email_in_use", return_value=False):
            response = self.patch({"email": "taken@example.com"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.json()["errors"])
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")

    def test_patch_allows_resaving_own_email(self):
        self.login("mine@example.com")
        self.assertEqual(self.patch({"email": "mine@example.com"}).status_code, 200)

    def test_many_users_may_have_no_email(self):
        get_user_model().objects.create_user(username="a", password="x")
        get_user_model().objects.create_user(username="b", password="x")
        self.assertEqual(get_user_model().objects.filter(email="").count(), 2)

    def test_patch_requires_login(self):
        self.assertEqual(self.patch({"email": "a@example.com"}).status_code, 401)

    def test_patch_enforces_csrf(self):
        user = self.login()
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(self.patch({"email": "a@example.com"}, client).status_code, 403)

        token = client.get("/api/auth/csrf").json()["csrfToken"]
        response = client.patch(
            "/api/auth/profile",
            data={"email": "a@example.com"},
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(response.status_code, 200)


class LogoutApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="logout-user", password="a-Long-unusual-pass-123"
        )
        self.client.force_login(self.user)

    def test_logout_clears_the_session(self):
        response = self.client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get("/api/auth/logout").status_code, 405)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post("/api/auth/logout").status_code, 403)

        token = client.get("/api/auth/csrf").json()["csrfToken"]
        response = client.post(
            "/api/auth/logout", headers={"X-CSRFToken": token}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)
