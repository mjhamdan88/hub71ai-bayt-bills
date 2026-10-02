# Generated manually to rename authorized_user to intended_account

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('unicom', '0013_callbackexecution'),
    ]

    operations = [
        migrations.RenameField(
            model_name='callbackexecution',
            old_name='authorized_user',
            new_name='intended_account',
        ),
    ]
