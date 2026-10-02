from django.conf import settings
from django.db import migrations


def refresh_status_summaries(apps, schema_editor):
    Communication = apps.get_model('unicrm', 'Communication')
    db_alias = schema_editor.connection.alias
    unsub_path = getattr(settings, 'UNICRM_UNSUBSCRIBE_PATH', '/unicrm/unsubscribe/')

    for communication in Communication.objects.using(db_alias).all().iterator():
        deliveries = communication.messages.using(db_alias).select_related('message')
        total = deliveries.count()
        failures = 0
        bounced = 0
        sent = 0
        opened = 0
        clicked = 0
        replied = 0
        unsubscribed = 0
        awaiting_dispatch = False
        has_started_sending = False

        for delivery in deliveries.iterator():
            metadata = delivery.metadata or {}
            meta_status = str(metadata.get('status') or '').lower()

            if getattr(delivery, 'has_received_reply', False):
                replied += 1
                continue

            status = meta_status or str(getattr(delivery, 'status', '') or '').lower()
            if not status:
                status = 'sent' if delivery.message_id else 'scheduled'

            if status == 'unsubscribed':
                unsubscribed += 1
                continue

            if status == 'bounced':
                bounced += 1
            elif status in {'failed', 'skipped'}:
                failures += 1
            elif status == 'sent':
                message = delivery.message
                if message:
                    links = []
                    try:
                        links = getattr(message, 'clicked_links', None) or []
                    except Exception:
                        links = []
                    if not links:
                        links = metadata.get('clicked_links') or []
                    if isinstance(links, str):
                        links = [links]

                    if getattr(message, 'bounced', False):
                        bounced += 1
                    elif getattr(message, 'link_clicked', False) or getattr(message, 'clicked_links', None):
                        filtered_links = [
                            (link or '')
                            for link in (getattr(message, 'clicked_links', []) or links)
                            if link and unsub_path not in link and 'unsubscribe' not in str(link).lower()
                        ]
                        if filtered_links:
                            clicked += 1
                        else:
                            sent += 1
                    elif getattr(message, 'opened', False) or getattr(message, 'seen', False):
                        opened += 1
                    else:
                        sent += 1
                    has_started_sending = True
                else:
                    sent += 1
            else:
                awaiting_dispatch = True

            if delivery.message_id:
                has_started_sending = True

        totals = {
            'total': total,
            'failed': failures,
            'sent': sent,
            'opened': opened,
            'clicked': clicked,
            'bounced': bounced,
            'replied': replied,
            'unsubscribed': unsubscribed,
        }

        new_status = communication.status
        if communication.status != 'cancelled':
            if totals['total'] == 0:
                if communication.status in {'scheduled', 'sending', 'ongoing'}:
                    new_status = communication.status
                elif communication.scheduled_for:
                    new_status = 'scheduled'
                else:
                    new_status = 'draft'
            elif awaiting_dispatch:
                if has_started_sending:
                    new_status = 'sending'
                else:
                    new_status = 'scheduled'
            else:
                new_status = 'ongoing' if communication.auto_enroll_new_contacts else 'completed'

        updates = []
        if communication.status_summary != totals:
            communication.status_summary = totals
            updates.append('status_summary')
        if new_status != communication.status:
            communication.status = new_status
            updates.append('status')

        if updates:
            communication.save(update_fields=updates + ['updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0020_communication_skip_antispam_guards'),
    ]

    operations = [
        migrations.RunPython(
            refresh_status_summaries,
            migrations.RunPython.noop,
        ),
    ]
