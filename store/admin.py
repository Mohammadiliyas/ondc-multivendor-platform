from django.contrib import admin
from .models import Vendor, Category, Product, Order, OrderItem, InventoryMovement, PaymentRecord, Shipment, ONDCTransaction, AuditLog, VendorFulfillment, PaymentWebhookEvent, RefundRecord, VendorSettlement

admin.site.register([Vendor, Category, Product, Order, OrderItem, InventoryMovement, PaymentRecord, Shipment, ONDCTransaction, AuditLog, VendorFulfillment, PaymentWebhookEvent, RefundRecord, VendorSettlement])
