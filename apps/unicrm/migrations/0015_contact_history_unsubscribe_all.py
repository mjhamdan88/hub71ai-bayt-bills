from django.db import migrations, models
import django.utils.timezone


def _history_for_contact(contact, CommunicationMessage, Message):
    deliveries = (
        CommunicationMessage.objects
        .filter(contact=contact)
        .select_related('communication', 'communication__channel', 'message')
        .order_by('-created_at')
    )
    history = []
    for delivery in deliveries:
        communication = delivery.communication
        message = delivery.message
        metadata = delivery.metadata or {}
        payload = metadata.get('payload') or {}
        channel = getattr(communication, 'channel', None)

        subject = None
        if message and getattr(message, 'subject', None):
            subject = message.subject
        elif payload:
            subject = payload.get('subject')
        elif communication and getattr(communication, 'subject_template', None):
            subject = communication.subject_template

        status = (delivery.status or '').strip() or (metadata.get('status') or '').strip()
        if not status:
            status = 'sent' if delivery.message_id else 'scheduled'

        direction = 'outbound'
        if message is not None and getattr(message, 'is_outgoing', None) is False:
            direction = 'inbound'

        sent_at = None
        opened_at = None
        clicked_at = None
        replied_at = None
        bounced_at = None

        if message:
            sent_at = message.time_sent or message.timestamp
            opened_at = message.time_opened or message.time_seen
            clicked_at = message.time_link_clicked
            bounced_at = message.time_bounced
            if getattr(delivery, 'replied_at', None):
                replied_at = delivery.replied_at
        else:
            sent_at = delivery.scheduled_at or (communication.scheduled_for if communication else None)

        history.append({
            'communication_id': communication.pk if communication else None,
            'communication_status': getattr(communication, 'status', None),
            'message_id': message.pk if message else None,
            'direction': direction,
            'channel': getattr(channel, 'platform', None),
            'status': status,
            'subject': subject,
            'sent_at': sent_at.isoformat() if sent_at else None,
            'opened_at': opened_at.isoformat() if opened_at else None,
            'clicked_at': clicked_at.isoformat() if clicked_at else None,
            'replied_at': replied_at.isoformat() if replied_at else None,
            'bounced_at': bounced_at.isoformat() if bounced_at else None,
            'created_at': delivery.created_at.isoformat() if delivery.created_at else None,
        })
    return history


def backfill_public_name_and_history(apps, schema_editor):
    MailingList = apps.get_model('unicrm', 'MailingList')
    Contact = apps.get_model('unicrm', 'Contact')
    CommunicationMessage = apps.get_model('unicrm', 'CommunicationMessage')
    Message = apps.get_model('unicom', 'Message')

    for ml in MailingList.objects.all():
        if not getattr(ml, 'public_name', None):
            ml.public_name = ml.name
            ml.save(update_fields=['public_name'])

    for contact in Contact.objects.all().iterator():
        history = _history_for_contact(contact, CommunicationMessage, Message)
        contact.communication_history = history
        contact.save(update_fields=['communication_history', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('unicom', '0017_add_chat_metadata'),
        ('unicrm', '0014_contact_gp_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='communication_history',
            field=models.JSONField(blank=True, default=list, help_text='Cached list of communications involving this contact.', verbose_name='Communication history'),
        ),
        migrations.AddField(
            model_name='mailinglist',
            name='public_name',
            field=models.CharField(default='', help_text='Name shown on public subscription pages.', max_length=255, verbose_name='Public name'),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='UnsubscribeAll',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('unsubscribed_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Unsubscribed at')),
                ('feedback', models.TextField(blank=True, verbose_name='Feedback')),
                ('communication', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='unsubscribe_events', to='unicrm.communication')),
                ('contact', models.ForeignKey(on_delete=models.CASCADE, related_name='unsubscribe_all_entries', to='unicrm.contact')),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='unsubscribe_events', to='unicom.message')),
            ],
            options={
                'ordering': ('-unsubscribed_at',),
            },
        ),
        migrations.RunPython(backfill_public_name_and_history, migrations.RunPython.noop),
    ]
