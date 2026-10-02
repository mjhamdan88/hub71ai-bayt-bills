from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0009_remove_unused_draft_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='communication',
            name='evergreen_refreshed_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Evergreen refreshed at',
                help_text='Last time evergreen auto-enrollment recomputed segment membership.',
            ),
        ),
    ]
