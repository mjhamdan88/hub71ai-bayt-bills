from django.db import migrations


def create_company_name_variable(apps, schema_editor):
    TemplateVariable = apps.get_model('unicrm', 'TemplateVariable')
    key = 'company_name_with_in'
    if TemplateVariable.objects.filter(key=key).exists():
        return

    TemplateVariable.objects.create(
        key=key,
        label='Company name phrase',
        description='Returns "in <company name>" when the contact has a non-empty company name.',
        code="""
def compute(contact):
    company = getattr(contact, 'company', None)
    name = getattr(company, 'name', '') if company else ''
    name = name.strip() if name else ''
    if not name:
        return ''
    return f'in {name}'
""",
        is_active=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0023_communication_exclude_follow_up_siblings'),
    ]

    operations = [
        migrations.RunPython(create_company_name_variable, migrations.RunPython.noop),
    ]
