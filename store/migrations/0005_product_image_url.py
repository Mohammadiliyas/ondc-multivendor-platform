from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('store', '0004_refunds_and_vendor_settlements')]
    operations = [migrations.AddField(model_name='product', name='image_url', field=models.URLField(blank=True, max_length=500))]
