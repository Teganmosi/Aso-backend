from django.core.management.base import BaseCommand
from apps.orders.services import cancel_expired_orders


class Command(BaseCommand):
    help = 'Cancels PENDING_PAYMENT orders past 30-minute reservation window and restores inventory stock.'

    def handle(self, *args, **options):
        self.stdout.write('Checking for expired unconfirmed orders...')
        count = cancel_expired_orders()
        self.stdout.write(self.style.SUCCESS(f'Successfully cancelled {count} expired order(s) and restored inventory stock.'))
