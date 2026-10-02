from django.db import migrations, models


def populate_provider_message_id(apps, schema_editor):
    Message = apps.get_model('unicom', 'Message')
    for msg in Message.objects.filter(platform='Telegram', provider_message_id__isnull=True):
        raw = msg.raw or {}
        raw_id = raw.get('message_id') or msg.id
        msg.provider_message_id = str(raw_id)
        msg.save(update_fields=['provider_message_id'])


def clear_provider_message_id(apps, schema_editor):
    Message = apps.get_model('unicom', 'Message')
    Message.objects.filter(platform='Telegram').update(provider_message_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('unicom', '0019_draftmessage_skip_reacher_validation'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='provider_message_id',
            field=models.CharField(blank=True, db_index=True, help_text='Raw provider message id (e.g., Telegram message_id)', max_length=500, null=True),
        ),
        migrations.RunPython(populate_provider_message_id, reverse_code=clear_provider_message_id),
    ]
