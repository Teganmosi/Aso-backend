from django.core.management.base import BaseCommand
from apps.orders.services import process_vendor_sla_timeouts


class Command(BaseCommand):
    help = 'Cancels PAID orders past 48-hour vendor acceptance SLA window and restores inventory stock.'

    def handle(self, *args, **options):
        self.stdout.write('Checking for orders exceeding vendor acceptance SLA...')
        count = process_vendor_sla_timeouts()
        self.stdout.write(self.style.SUCCESS(f'Successfully cancelled {count} order(s) due to vendor SLA timeout and restored inventory stock.'))
