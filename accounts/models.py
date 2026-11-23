from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class LoginAttempt(models.Model):
    """Failed login attempts per username or client IP in a fixed time window."""

    class Scope(models.TextChoices):
        USERNAME = "USERNAME", "Username"
        IP = "IP", "IP address"

    scope = models.CharField(max_length=8, choices=Scope.choices)
    identifier = models.CharField(max_length=150)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "identifier", "window_start"],
                name="unique_login_attempt_window",
            ),
        ]
        indexes = [models.Index(fields=["window_start"])]

    def __str__(self):
        return f"{self.scope} {self.identifier}: {self.count}"


class QuotaLock(models.Model):
    """Single row locked to serialize global quota checks (users, API keys)."""

    @classmethod
    def acquire(cls):
        """Lock the row; must be called inside transaction.atomic()."""
        cls.objects.get_or_create(pk=1)
        return cls.objects.select_for_update().get(pk=1)


class User(AbstractUser):
    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="unique_user_email_ci",
            )
        ]
