from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0018_communication_mailing_list'),
    ]

    operations = [
        migrations.AddField(
            model_name='communication',
            name='follow_up_for',
            field=models.ForeignKey(
                blank=True,
                help_text='Optional parent communication this one follows up on.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='followups',
                to='unicrm.communication',
            ),
        ),
        migrations.AddField(
            model_name='segment',
            name='for_followup',
            field=models.BooleanField(
                default=False,
                help_text='Auto-detected flag when the segment uses `previous_comm` in its code.',
                verbose_name='Requires previous communication',
            ),
        ),
    ]
