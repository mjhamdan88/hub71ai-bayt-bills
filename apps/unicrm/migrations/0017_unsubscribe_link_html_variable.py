from django.db import migrations


def ensure_unsubscribe_variables(apps, schema_editor):
    TemplateVariable = apps.get_model('unicrm', 'TemplateVariable')

    if not TemplateVariable.objects.filter(key='unsubscribe_link').exists():
        TemplateVariable.objects.create(
            key='unsubscribe_link',
            label='Unsubscribe link',
            description='Returns a ready-to-use <a> tag with the unsubscribe URL.',
            code="""
def compute(contact):
    from unicrm.services.unsubscribe_links import build_unsubscribe_link
    link = build_unsubscribe_link(contact)
    return f'<a href="{link}">Unsubscribe</a>'
""",
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0016_add_unsubscribe_template_variable'),
    ]

    operations = [
        migrations.RunPython(ensure_unsubscribe_variables, migrations.RunPython.noop),
    ]
