from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('store', '0003_razorpay_payments')]
    operations = [
        migrations.CreateModel(
            name='RefundRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('razorpay_refund_id', models.CharField(blank=True, max_length=180, null=True, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('status', models.CharField(choices=[('PENDING','Pending'),('PROCESSED','Processed'),('FAILED','Failed')], default='PENDING', max_length=16)),
                ('reason', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='refunds', to='store.paymentrecord')),
            ],
        ),
        migrations.CreateModel(
            name='VendorSettlement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('gross_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('platform_fee', models.DecimalField(decimal_places=2, max_digits=12)),
                ('net_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('status', models.CharField(choices=[('PENDING','Pending'),('READY','Ready for manual payout'),('PAID','Paid'),('HELD','Held')], default='PENDING', max_length=16)),
                ('payout_reference', models.CharField(blank=True, max_length=180)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='vendor_settlements', to='store.order')),
                ('vendor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='settlements', to='store.vendor')),
            ],
            options={'constraints':[models.UniqueConstraint(fields=('order','vendor'), name='unique_order_vendor_settlement')]},
        ),
    ]
