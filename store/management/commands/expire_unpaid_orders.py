from datetime import timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from store.models import Order, Product, InventoryMovement, PaymentRecord, VendorFulfillment

class Command(BaseCommand):
    help = 'Cancel expired unpaid marketplace orders and release reserved inventory.'

    def add_arguments(self, parser):
        parser.add_argument('--minutes', type=int, default=None)

    def handle(self, *args, **options):
        minutes = options['minutes'] or settings.UNPAID_ORDER_EXPIRY_MINUTES
        if minutes < 1:
            self.stderr.write('Expiry minutes must be at least 1.')
            return
        cutoff = timezone.now() - timedelta(minutes=minutes)
        candidates = Order.objects.filter(status=Order.Status.PLACED, created_at__lt=cutoff).order_by('created_at')
        expired = 0
        for candidate in candidates.iterator():
            with transaction.atomic():
                try:
                    order = Order.objects.select_for_update().get(pk=candidate.pk)
                except Order.DoesNotExist:
                    continue
                if order.status != Order.Status.PLACED or order.created_at >= cutoff:
                    continue
                if order.payments.filter(status__in=[PaymentRecord.Status.AUTHORIZED, PaymentRecord.Status.PAID, PaymentRecord.Status.REFUNDED]).exists():
                    continue
                if order.vendor_fulfillments.exclude(status=VendorFulfillment.Status.PENDING).exists():
                    continue
                for item in order.items.select_related('product').all():
                    product = Product.objects.select_for_update().get(pk=item.product_id)
                    product.stock += item.quantity
                    product.save(update_fields=['stock', 'updated_at'])
                    InventoryMovement.objects.create(product=product, quantity_delta=item.quantity, reason=f'Unpaid order expiry {order.pk}')
                order.status = Order.Status.CANCELLED
                order.save(update_fields=['status'])
                order.vendor_fulfillments.update(status=VendorFulfillment.Status.CANCELLED)
                expired += 1
        self.stdout.write(self.style.SUCCESS(f'Expired {expired} unpaid order(s) older than {minutes} minute(s).'))
