from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('unicrm', '0003_remove_template_add_content'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contact',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name='Email'),
        ),
    ]
