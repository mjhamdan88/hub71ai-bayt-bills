from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0019_communication_follow_up_for_segment_for_followup'),
    ]

    operations = [
        migrations.AddField(
            model_name='communication',
            name='skip_antispam_guards',
            field=models.BooleanField(
                default=False,
                help_text='Send even if cooldown/unengaged limits would normally skip this contact.',
                verbose_name='Skip anti-spam guards',
            ),
        ),
    ]
