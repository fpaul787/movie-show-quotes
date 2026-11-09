from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from quotes.models import Character, Media, Quote


class Command(BaseCommand):
    help = "Load the quote fixture if all quote-related tables are empty."

    def handle(self, *args, **options):
        models = (Media, Character, Quote)
        with transaction.atomic():
            if connection.vendor == "postgresql":
                tables = ", ".join(
                    connection.ops.quote_name(model._meta.db_table) for model in models
                )
                with connection.cursor() as cursor:
                    cursor.execute(f"LOCK TABLE {tables} IN SHARE ROW EXCLUSIVE MODE")

            if any(model.objects.exists() for model in models):
                self.stdout.write("Skipping quote seed: quote-related data already exists.")
                return

            call_command("loaddata", "quotes", stdout=self.stdout, stderr=self.stderr)
