from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unicom', '0022_toolcall_result_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='toolcall',
            name='progress_updates_for_user',
            field=models.TextField(blank=True, help_text='LLM-provided one-line description of what/why this call is doing', null=True),
        ),
    ]
