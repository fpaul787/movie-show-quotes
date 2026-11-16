from django.contrib.auth import get_user_model
from django.test import TestCase


class HomepageTests(TestCase):
    def test_root_serves_react_homepage(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, '<div id="root" data-username=""></div>', html=False
        )

    def test_root_includes_logged_in_username(self):
        user = get_user_model().objects.create_user(
            username="homepage-user", password="a-Long-unusual-pass-123"
        )
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-username="homepage-user"')

    def test_legacy_homepage_url_redirects_to_root(self):
        response = self.client.get("/homepage/")

        self.assertRedirects(
            response, "/", status_code=301, fetch_redirect_response=False
        )

    def test_signup_page_serves_the_react_app(self):
        response = self.client.get("/signup/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"')

    def test_login_page_serves_the_react_app(self):
        response = self.client.get("/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"')

    def test_profile_api_keys_page_serves_the_react_app(self):
        response = self.client.get("/profile/api-keys/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<div id="root"')
