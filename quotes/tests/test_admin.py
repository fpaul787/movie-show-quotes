from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ..models import Character, Media, Quote


class CharacterAdminTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser(
            username="admin", password="test-password"
        )
        self.client.force_login(admin)
        self.media = Media.objects.create(
            title="Original", media_type="MOVIE", release_year=2000
        )
        self.other = Media.objects.create(
            title="Other", media_type="MOVIE", release_year=2001
        )
        self.character = Character.objects.create(name="Speaker", media=self.media)
        self.url = reverse("admin:quotes_character_change", args=[self.character.pk])

    def test_media_is_read_only_when_character_has_quotes(self):
        quote = Quote.objects.create(
            text="Hello", media=self.media, character=self.character, language="en"
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, 'name="media"')

        response = self.client.post(
            self.url, {"name": "Renamed", "media": self.other.pk, "_save": "Save"}
        )
        self.assertEqual(response.status_code, 302)
        self.character.refresh_from_db()
        quote.refresh_from_db()
        self.assertEqual(self.character.name, "Renamed")
        self.assertEqual(self.character.media_id, self.media.pk)
        self.assertEqual(quote.media_id, self.character.media_id)

    def test_media_can_be_changed_without_quotes(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="media"')

        response = self.client.post(
            self.url, {"name": "Speaker", "media": self.other.pk, "_save": "Save"}
        )
        self.assertEqual(response.status_code, 302)
        self.character.refresh_from_db()
        self.assertEqual(self.character.media_id, self.other.pk)

    def test_duplicate_name_is_rejected_when_media_is_read_only(self):
        Quote.objects.create(
            text="Hello", media=self.media, character=self.character, language="en"
        )
        Character.objects.create(name="Another", media=self.media)

        response = self.client.post(
            self.url, {"name": "Another", "_save": "Save"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["adminform"].form,
            "name",
            "A character with this name already exists for this media.",
        )
        self.character.refresh_from_db()
        self.assertEqual(self.character.name, "Speaker")

    def test_media_is_editable_when_adding_character(self):
        response = self.client.get(reverse("admin:quotes_character_add"))
        self.assertContains(response, 'name="media"')
