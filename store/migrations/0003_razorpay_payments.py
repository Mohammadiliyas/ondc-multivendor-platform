from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('store', '0002_vendor_fulfillment')]
    operations = [
        migrations.AlterField(
            model_name='paymentrecord', name='provider',
            field=models.CharField(default='razorpay', max_length=80),
        ),
        migrations.AlterField(
            model_name='paymentrecord', name='status',
            field=models.CharField(choices=[('PENDING','Pending'),('AUTHORIZED','Authorized'),('PAID','Paid'),('FAILED','Failed'),('REFUNDED','Refunded')], default='PENDING', max_length=32),
        ),
        migrations.AddField(model_name='paymentrecord', name='amount', field=models.DecimalField(decimal_places=2, default=0, max_digits=12)),
        migrations.AddField(model_name='paymentrecord', name='currency', field=models.CharField(default='INR', max_length=3)),
        migrations.AddField(model_name='paymentrecord', name='razorpay_order_id', field=models.CharField(blank=True, max_length=180, null=True, unique=True)),
        migrations.AddField(model_name='paymentrecord', name='razorpay_payment_id', field=models.CharField(blank=True, max_length=180, null=True, unique=True)),
        migrations.AddField(model_name='paymentrecord', name='signature_verified', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='paymentrecord', name='paid_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='paymentrecord', name='failure_reason', field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name='paymentrecord', name='updated_at', field=models.DateTimeField(auto_now=True)),
        migrations.AddConstraint(model_name='paymentrecord', constraint=models.UniqueConstraint(fields=('order','provider'), name='unique_order_payment_provider')),
        migrations.CreateModel(
            name='PaymentWebhookEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider_event_id', models.CharField(max_length=180, unique=True)),
                ('event_type', models.CharField(max_length=80)),
                ('processed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='webhook_events', to='store.paymentrecord')),
            ],
        ),
    ]
