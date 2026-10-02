from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unicom', '0020_message_provider_message_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='open_count',
            field=models.PositiveIntegerField(default=0, help_text='Number of times the email open pixel was fetched'),
        ),
    ]
