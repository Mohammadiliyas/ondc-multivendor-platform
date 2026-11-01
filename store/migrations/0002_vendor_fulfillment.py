from django.db import migrations, models
import django.db.models.deletion

def create_existing_fulfillments(apps, schema_editor):
    Order = apps.get_model('store', 'Order')
    OrderItem = apps.get_model('store', 'OrderItem')
    VendorFulfillment = apps.get_model('store', 'VendorFulfillment')
    for order in Order.objects.all().iterator():
        vendor_ids = OrderItem.objects.filter(order_id=order.pk).values_list('product__vendor_id', flat=True).distinct()
        for vendor_id in vendor_ids:
            VendorFulfillment.objects.get_or_create(
                order_id=order.pk, vendor_id=vendor_id,
                defaults={'status': order.status if order.status in ['CANCELLED','DELIVERED'] else 'PENDING'}
            )

class Migration(migrations.Migration):
    dependencies = [('store', '0001_initial')]
    operations = [
        migrations.CreateModel(
            name='VendorFulfillment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PENDING','Pending'),('CONFIRMED','Confirmed'),('PACKED','Packed'),('SHIPPED','Shipped'),('DELIVERED','Delivered'),('CANCELLED','Cancelled')], default='PENDING', max_length=16)),
                ('tracking_reference', models.CharField(blank=True, max_length=180)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vendor_fulfillments', to='store.order')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fulfillments', to='store.vendor')),
            ],
            options={'ordering':['created_at']},
        ),
        migrations.AddConstraint(
            model_name='vendorfulfillment',
            constraint=models.UniqueConstraint(fields=('order','vendor'), name='unique_order_vendor_fulfillment'),
        ),
        migrations.RunPython(create_existing_fulfillments, migrations.RunPython.noop),
    ]
