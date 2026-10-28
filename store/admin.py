from django.contrib import admin
from .models import Vendor, Category, Product, Order, OrderItem, InventoryMovement, PaymentRecord, Shipment, ONDCTransaction, AuditLog

admin.site.register([Vendor, Category, Product, Order, OrderItem, InventoryMovement, PaymentRecord, Shipment, ONDCTransaction, AuditLog])
