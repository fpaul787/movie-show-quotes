import hashlib
import hmac
import secrets

from django.conf import settings
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
        self.prefix = secrets.token_hex(4)
        raw_key = f"{self.prefix}.{secrets.token_urlsafe(32)}"
        self.hashed_key = self._hash(raw_key)
        return raw_key

    @classmethod
    def authenticate(cls, raw_key):
        """Return the matching usable APIKey, or None."""
        prefix, sep, _ = (raw_key or "").partition(".")
        if not sep:
            return None
        key = cls.objects.filter(prefix=prefix).first()
        if key is None or not hmac.compare_digest(key.hashed_key, cls._hash(raw_key)):
            return None
        return key

    def is_usable(self):
        if not self.is_active:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


class Quote(models.Model):
    text = models.TextField()
    year = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=255)
    character = models.CharField(max_length=255)
    source = models.CharField(max_length=50)
    language = models.CharField(max_length=50)
    tags = models.JSONField(default=list)
    created_at = models.DateField()

    def __str__(self):
        return f"{self.title} — {self.character}"
