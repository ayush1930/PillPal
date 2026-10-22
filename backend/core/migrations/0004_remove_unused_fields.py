from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_dispute_models'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='address',
            name='latitude',
        ),
        migrations.RemoveField(
            model_name='address',
            name='longitude',
        ),
        migrations.RemoveField(
            model_name='medication',
            name='barcode',
        ),
        migrations.RemoveField(
            model_name='pharmacy',
            name='latitude',
        ),
        migrations.RemoveField(
            model_name='pharmacy',
            name='longitude',
        ),
    ]
