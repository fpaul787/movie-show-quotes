from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import LoginAttempt
from quotes import ratelimit


class Command(BaseCommand):
    help = "Delete API usage and login attempt counters older than --days (default 2)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=2)

    def handle(self, *args, **options):
        if options["days"] < 0:
            raise CommandError("--days must not be negative.")
        cutoff = timezone.now() - timedelta(days=options["days"])
        usage = ratelimit.prune(cutoff)
        attempts, _ = LoginAttempt.objects.filter(window_start__lt=cutoff).delete()
        self.stdout.write(
            f"Deleted {usage} API usage and {attempts} login attempt windows."
        )
