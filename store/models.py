from django.conf import settings
from django.db import models

class Vendor(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vendor_profile')
    store_name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.store_name

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.name

class Product(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    sku = models.CharField(max_length=80, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: ordering = ['name']
    def __str__(self): return self.name

class Order(models.Model):
    class Status(models.TextChoices):
        PLACED='PLACED','Placed'; CONFIRMED='CONFIRMED','Confirmed'; PACKED='PACKED','Packed'; SHIPPED='SHIPPED','Shipped'; DELIVERED='DELIVERED','Delivered'; CANCELLED='CANCELLED','Cancelled'
    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='marketplace_orders')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLACED)
    shipping_address = models.TextField()
    idempotency_key = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=180)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField()

class InventoryMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_movements')
    quantity_delta = models.IntegerField()
    reason = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        AUTHORIZED = 'AUTHORIZED', 'Authorized'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    provider = models.CharField(max_length=80, default='razorpay')
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=180, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='INR')
    razorpay_order_id = models.CharField(max_length=180, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=180, unique=True, null=True, blank=True)
    signature_verified = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'provider'], name='unique_order_payment_provider')]


class Shipment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='shipments')
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT)
    status = models.CharField(max_length=32, default='PENDING')
    tracking_reference = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class ONDCTransaction(models.Model):
    transaction_id = models.CharField(max_length=180, db_index=True)
    message_id = models.CharField(max_length=180, db_index=True)
    action = models.CharField(max_length=40)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=32, default='RECEIVED')
    created_at = models.DateTimeField(auto_now_add=True)

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class VendorFulfillment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        PACKED = 'PACKED', 'Packed'
        SHIPPED = 'SHIPPED', 'Shipped'
        DELIVERED = 'DELIVERED', 'Delivered'
        CANCELLED = 'CANCELLED', 'Cancelled'
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='vendor_fulfillments')
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='fulfillments')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    tracking_reference = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'vendor'], name='unique_order_vendor_fulfillment')]
        ordering = ['created_at']
    def __str__(self):
        return f'Order {self.order_id} · {self.vendor.store_name}'

class PaymentWebhookEvent(models.Model):
    provider_event_id = models.CharField(max_length=180, unique=True)
    event_type = models.CharField(max_length=80)
    payment = models.ForeignKey(PaymentRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='webhook_events')
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class RefundRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSED = 'PROCESSED', 'Processed'
        FAILED = 'FAILED', 'Failed'
    payment = models.ForeignKey(PaymentRecord, on_delete=models.PROTECT, related_name='refunds')
    razorpay_refund_id = models.CharField(max_length=180, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class VendorSettlement(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        READY = 'READY', 'Ready for manual payout'
        PAID = 'PAID', 'Paid'
        HELD = 'HELD', 'Held'
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='vendor_settlements')
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='settlements')
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    payout_reference = models.CharField(max_length=180, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order', 'vendor'], name='unique_order_vendor_settlement')]
