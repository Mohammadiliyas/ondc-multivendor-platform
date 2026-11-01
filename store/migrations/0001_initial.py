# Generated initial migration for the marketplace domain models.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('name', models.CharField(max_length=100, unique=True))],
        ),
        migrations.CreateModel(
            name='Vendor',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('store_name', models.CharField(max_length=160)), ('description', models.TextField(blank=True)), ('is_approved', models.BooleanField(default=False)), ('is_suspended', models.BooleanField(default=False)), ('created_at', models.DateTimeField(auto_now_add=True)), ('owner', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vendor_profile', to=settings.AUTH_USER_MODEL))],
        ),
        migrations.CreateModel(
            name='Product',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('name', models.CharField(max_length=180)), ('description', models.TextField(blank=True)), ('sku', models.CharField(max_length=80, unique=True)), ('price', models.DecimalField(decimal_places=2, max_digits=12)), ('stock', models.PositiveIntegerField(default=0)), ('is_active', models.BooleanField(default=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)), ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products', to='store.category')), ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='store.vendor'))],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Order',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('status', models.CharField(choices=[('PLACED','Placed'),('CONFIRMED','Confirmed'),('PACKED','Packed'),('SHIPPED','Shipped'),('DELIVERED','Delivered'),('CANCELLED','Cancelled')], default='PLACED', max_length=16)), ('shipping_address', models.TextField()), ('idempotency_key', models.CharField(max_length=100, unique=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('buyer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='marketplace_orders', to=settings.AUTH_USER_MODEL))],
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('product_name', models.CharField(max_length=180)), ('unit_price', models.DecimalField(decimal_places=2, max_digits=12)), ('quantity', models.PositiveIntegerField()), ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='store.order')), ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='store.product'))],
        ),
        migrations.CreateModel(
            name='InventoryMovement',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('quantity_delta', models.IntegerField()), ('reason', models.CharField(max_length=120)), ('created_at', models.DateTimeField(auto_now_add=True)), ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inventory_movements', to='store.product'))],
        ),
        migrations.CreateModel(
            name='PaymentRecord',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('provider', models.CharField(default='manual', max_length=80)), ('status', models.CharField(default='PENDING', max_length=32)), ('provider_reference', models.CharField(blank=True, max_length=180)), ('created_at', models.DateTimeField(auto_now_add=True)), ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='store.order'))],
        ),
        migrations.CreateModel(
            name='Shipment',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('status', models.CharField(default='PENDING', max_length=32)), ('tracking_reference', models.CharField(blank=True, max_length=180)), ('created_at', models.DateTimeField(auto_now_add=True)), ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shipments', to='store.order')), ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='store.vendor'))],
        ),
        migrations.CreateModel(
            name='ONDCTransaction',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('transaction_id', models.CharField(db_index=True, max_length=180)), ('message_id', models.CharField(db_index=True, max_length=180)), ('action', models.CharField(max_length=40)), ('payload', models.JSONField(default=dict)), ('status', models.CharField(default='RECEIVED', max_length=32)), ('created_at', models.DateTimeField(auto_now_add=True))],
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('action', models.CharField(max_length=120)), ('object_type', models.CharField(blank=True, max_length=100)), ('object_id', models.CharField(blank=True, max_length=100)), ('details', models.JSONField(blank=True, default=dict)), ('created_at', models.DateTimeField(auto_now_add=True)), ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL))],
        ),
    ]
