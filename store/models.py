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
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='payments')
    provider = models.CharField(max_length=80, default='manual')
    status = models.CharField(max_length=32, default='PENDING')
    provider_reference = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
