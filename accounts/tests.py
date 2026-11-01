from django.contrib.auth import get_user_model
from django.test import Client, TestCase

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
