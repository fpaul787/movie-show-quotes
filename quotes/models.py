import hashlib
import hmac
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class APIKey(models.Model):
    name = models.CharField(max_length=100, help_text="Who or what this key is for")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    prefix = models.CharField(max_length=8, unique=True, editable=False)
    hashed_key = models.CharField(max_length=64, editable=False)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True, editable=False)

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @staticmethod
    def _hash(raw_key):
        return hashlib.sha256(raw_key.encode()).hexdigest()

    def set_new_key(self):
        """Generate a key, store its hash, and return the raw key (shown once)."""
        while True:
            self.prefix = secrets.token_hex(4)
            if not APIKey.objects.filter(prefix=self.prefix).exists():
                break
        raw_key = f"{self.prefix}.{secrets.token_urlsafe(32)}"
        self.hashed_key = self._hash(raw_key)
        return raw_key

    @classmethod
    def authenticate(cls, raw_key):
        """Return the matching usable APIKey, or None."""
        prefix, sep, _ = (raw_key or "").partition(".")
        if not sep:
            return None
        key = cls.objects.select_related("owner").filter(prefix=prefix).first()
        if key is None or not hmac.compare_digest(key.hashed_key, cls._hash(raw_key)):
            return None
        return key

    def is_revoked(self):
        # Keys of deactivated users are treated as revoked.
        return not self.is_active or (
            self.owner_id is not None and not self.owner.is_active
        )

    def is_usable(self):
        if self.is_revoked():
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


LANGUAGE_CODE_VALIDATOR = RegexValidator(
    r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$",
    "Enter a lowercase ISO 639 language code, e.g. 'en' or 'pt-BR'.",
)


class Media(models.Model):
    class MediaType(models.TextChoices):
        MOVIE = "MOVIE", "Movie"
        TV_SHOW = "TV_SHOW", "TV Show"

    title = models.CharField(max_length=255)
    media_type = models.CharField(max_length=10, choices=MediaType.choices)
    release_year = models.PositiveSmallIntegerField()
    external_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "media"
        indexes = [
            models.Index(fields=["title"]),
            models.Index(fields=["media_type", "release_year"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["external_id"],
                condition=models.Q(external_id__isnull=False),
                name="unique_media_external_id",
            ),
            models.UniqueConstraint(
                fields=["title", "media_type", "release_year"],
                name="unique_media_title_type_year",
            ),
        ]

    @staticmethod
    def normalize_media_type(value):
        return str(value).strip().upper().replace("-", "_").replace(" ", "_")

    def clean(self):
        super().clean()
        if self.media_type:
            self.media_type = self.normalize_media_type(self.media_type)
        if self.external_id == "":
            self.external_id = None

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.release_year})"


class Character(models.Model):
    name = models.CharField(max_length=255)
    media = models.ForeignKey(
        Media, on_delete=models.CASCADE, related_name="characters"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["name"])]
        constraints = [
            models.UniqueConstraint(
                fields=["media", "name"], name="unique_character_name_per_media"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.media.title})"


class Quote(models.Model):
    text = models.TextField()
    media = models.ForeignKey(
        Media, on_delete=models.CASCADE, related_name="quotes"
    )
    character = models.ForeignKey(
        Character,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotes",
    )
    language = models.CharField(
        max_length=16, validators=[LANGUAGE_CODE_VALIDATOR]
    )
    tags = models.JSONField(default=list)
    # Preserved from the legacy Quote.created_at, which was a user-entered date.
    original_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["language"]),
            models.Index(fields=["media", "character"]),
        ]

    def clean(self):
        super().clean()
        if (
            self.character_id
            and self.media_id
            and self.character.media_id != self.media_id
        ):
            raise ValidationError(
                {"character": "Character must belong to the quote's media."}
            )
        if not isinstance(self.tags, list) or not all(
            isinstance(t, str) for t in self.tags
        ):
            raise ValidationError({"tags": "Tags must be a list of strings."})

    def __str__(self):
        speaker = self.character.name if self.character_id else "Unknown"
        return f"{self.media.title} — {speaker}"
