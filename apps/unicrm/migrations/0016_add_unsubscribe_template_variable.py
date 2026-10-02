from django.db import migrations


def create_unsubscribe_variable(apps, schema_editor):
    TemplateVariable = apps.get_model('unicrm', 'TemplateVariable')
    key = 'unsubscribe_link'
    if TemplateVariable.objects.filter(key=key).exists():
        return
    TemplateVariable.objects.create(
        key=key,
        label='Unsubscribe link',
        description='Returns an absolute unsubscribe URL for this contact (and mailing list when available).',
        code="""
def compute(contact):
    from unicrm.services.unsubscribe_links import build_unsubscribe_link
    return build_unsubscribe_link(contact)
""",
        is_active=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0015_contact_history_unsubscribe_all'),
    ]

    operations = [
        migrations.RunPython(create_unsubscribe_variable, migrations.RunPython.noop),
    ]
