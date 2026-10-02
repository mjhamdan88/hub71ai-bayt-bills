from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('unicrm', '0012_company_attributes_company_industry'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='insight_id',
            field=models.CharField(
                verbose_name='GetProspect insight id',
                max_length=64,
                unique=True,
                null=True,
                blank=True,
                help_text='External lead identifier from GetProspect; used for email retrieval.',
            ),
        ),
    ]
