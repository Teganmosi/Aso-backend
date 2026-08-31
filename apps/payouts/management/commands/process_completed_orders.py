from django.core.management.base import BaseCommand
from apps.payouts.services import process_completed_orders


class Command(BaseCommand):
    help = 'Auto-completes delivered orders older than 72 hours and releases pending funds.'

    def handle(self, *args, **options):
        self.stdout.write("Running 72-hour Customer Protection Window auto-completion task...")
        completed = process_completed_orders()
        self.stdout.write(self.style.SUCCESS(f"Successfully completed {completed} order(s)."))
