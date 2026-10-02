from django.db import migrations, models


def populate_content_from_template(apps, schema_editor):
    Communication = apps.get_model('unicrm', 'Communication')
    MessageTemplate = apps.get_model('unicom', 'MessageTemplate')

    template_map = {
        template.pk: template.content or ''
        for template in MessageTemplate.objects.all()
    }

    updates = []
    for communication in Communication.objects.all():
        if getattr(communication, 'content', None):
            continue
        template_id = getattr(communication, 'template_id', None)
        if not template_id:
            continue
        communication.content = template_map.get(template_id, '')
        updates.append(communication)

    if updates:
        Communication.objects.bulk_update(updates, ['content'])

class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0002_alter_communicationmessage_unique_together_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='communication',
            name='content',
            field=models.TextField(
                blank=True,
                help_text='HTML content customised specifically for this communication.',
                verbose_name='Content',
            ),
        ),
        migrations.RunPython(populate_content_from_template, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='communication',
            name='template',
        ),
    ]
