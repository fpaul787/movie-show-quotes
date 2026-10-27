from django.contrib.auth import get_user_model
from django.test import TestCase

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
