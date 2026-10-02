from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0017_unsubscribe_link_html_variable'),
    ]

    operations = [
        migrations.AddField(
            model_name='communication',
            name='mailing_list',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='communications', to='unicrm.mailinglist'),
        ),
    ]
