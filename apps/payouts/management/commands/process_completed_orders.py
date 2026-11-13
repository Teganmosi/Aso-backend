from django.core.management.base import BaseCommand
from apps.payouts.services import process_completed_orders


class Command(BaseCommand):
    help = 'Auto-completes delivered orders older than 72 hours and releases pending funds.'

    def handle(self, *args, **options):
        self.stdout.write("Releasing designer payments for orders delivered more than 48 hours ago (no problem reported)...")
        completed = process_completed_orders()
        self.stdout.write(self.style.SUCCESS(f"Successfully completed {completed} order(s)."))
