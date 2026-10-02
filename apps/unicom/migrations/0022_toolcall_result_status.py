from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unicom', '0021_message_open_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='toolcall',
            name='result_status',
            field=models.CharField(choices=[('SUCCESS', 'Success'), ('WARNING', 'Warning'), ('ERROR', 'Error')], default='SUCCESS', help_text='Outcome reported by the tool (independent of processing status)', max_length=20),
        ),
    ]
