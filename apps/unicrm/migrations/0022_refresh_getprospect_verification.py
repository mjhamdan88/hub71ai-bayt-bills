from django.conf import settings
from django.db import migrations
import time


def refresh_verification_statuses(apps, schema_editor):
    from unicrm.models import Contact

    api_key = getattr(settings, 'GETPROSPECT_API_KEY', None)
    if not api_key:
        return

    queryset = (
        Contact.objects.filter(insight_id__isnull=False)
        .exclude(email__isnull=True)
        .exclude(email='')
    )

    for contact in queryset.iterator(chunk_size=100):
        try:
            contact.refresh_getprospect_verification(api_key=api_key)
        except Exception:
            continue
        time.sleep(0.2)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0021_fix_unsubscribe_counts'),
    ]

    operations = [
        migrations.RunPython(refresh_verification_statuses, noop),
    ]
