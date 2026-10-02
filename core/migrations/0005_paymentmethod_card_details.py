from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0004_message_metadata_actionrequest_paymentmethod_and_more')]
    operations = [
        migrations.AddField(model_name='paymentmethod', name='cardholder', field=models.CharField(max_length=100, blank=True)),
        migrations.AddField(model_name='paymentmethod', name='expiry', field=models.CharField(max_length=7, blank=True)),
    ]
