from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0013_contact_insight_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='gp_requested_at',
            field=models.DateTimeField(
                verbose_name='GetProspect requested at',
                null=True,
                blank=True,
                help_text='Timestamp when a GetProspect email request was initiated for this contact.',
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name='contact',
            name='gp_email_checked_at',
            field=models.DateTimeField(
                verbose_name='GetProspect email checked at',
                null=True,
                blank=True,
                help_text='Last time we polled GetProspect for this contact’s email.',
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name='contact',
            name='gp_email_status',
            field=models.CharField(
                verbose_name='GetProspect email status',
                max_length=20,
                blank=True,
                help_text='Status of GetProspect email lookup (e.g. pending, valid, invalid, not_found).',
                db_index=True,
            ),
        ),
    ]
