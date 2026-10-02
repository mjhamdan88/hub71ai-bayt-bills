from django.db import migrations


def add_email_from_name(apps, schema_editor):
    Channel = apps.get_model('unicom', 'Channel')
    for channel in Channel.objects.filter(platform='Email'):
        config = channel.config or {}
        if not isinstance(config, dict):
            continue
        if config.get('EMAIL_FROM_NAME'):
            continue
        email_address = (config.get('EMAIL_ADDRESS') or '').strip()
        if not email_address or '@' not in email_address:
            continue
        local_part = email_address.split('@', 1)[0].strip()
        if not local_part:
            continue
        config = dict(config)
        config['EMAIL_FROM_NAME'] = local_part
        Channel.objects.filter(pk=channel.pk).update(config=config)


class Migration(migrations.Migration):

    dependencies = [
        ('unicom', '0023_toolcall_progress_updates_for_user'),
    ]

    operations = [
        migrations.RunPython(add_email_from_name, migrations.RunPython.noop),
    ]
