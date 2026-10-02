from __future__ import annotations

from django.db import migrations, models
from django.utils.dateparse import parse_datetime


def populate_message_status(apps, schema_editor):
    CommunicationMessage = apps.get_model('unicrm', 'CommunicationMessage')
    for message in CommunicationMessage.objects.all().iterator():
        metadata = message.metadata or {}
        status = str(metadata.get('status') or 'scheduled').lower()
        if status not in {'scheduled', 'sent', 'failed', 'bounced', 'skipped'}:
            status = 'scheduled'
        send_at_str = metadata.get('send_at')
        scheduled_at = parse_datetime(send_at_str) if send_at_str else None
        message.status = status
        message.scheduled_at = scheduled_at
        message.save(update_fields=['status', 'scheduled_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0006_contact_email_bounce_type_contact_email_bounced_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='communication',
            name='auto_enroll_new_contacts',
            field=models.BooleanField(
                default=False,
                help_text='Automatically prepare and send this communication to contacts who later join the segment.',
                verbose_name='Auto-enroll new contacts',
            ),
        ),
        migrations.AddField(
            model_name='communicationmessage',
            name='status',
            field=models.CharField(
                choices=[
                    ('scheduled', 'Scheduled'),
                    ('sent', 'Sent'),
                    ('failed', 'Failed'),
                    ('bounced', 'Bounced'),
                    ('skipped', 'Skipped'),
                ],
                default='scheduled',
                max_length=20,
                verbose_name='Status',
            ),
        ),
        migrations.AddField(
            model_name='communicationmessage',
            name='scheduled_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Scheduled at'),
        ),
        migrations.AddIndex(
            model_name='communicationmessage',
            index=models.Index(fields=['status', 'scheduled_at'], name='unicrm_msg_status_sched_idx'),
        ),
        migrations.RunPython(populate_message_status, migrations.RunPython.noop),
    ]
