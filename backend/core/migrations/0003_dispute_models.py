import core.features.disputes.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_medication_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='Dispute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subject', models.CharField(max_length=180)),
                ('category', models.CharField(choices=[('order', 'Order problem'), ('delivery', 'Delivery problem'), ('medication', 'Medication problem'), ('payment', 'Payment query'), ('other', 'Other')], max_length=20)),
                ('description', models.TextField(max_length=4000)),
                ('evidence', models.FileField(blank=True, upload_to=core.features.disputes.models.evidence_path)),
                ('status', models.CharField(choices=[('open', 'Open'), ('under_review', 'Under review'), ('resolved', 'Resolved'), ('rejected', 'Rejected')], default='open', max_length=20)),
                ('admin_response', models.TextField(blank=True, max_length=4000)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('version', models.PositiveIntegerField(default=0)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='disputes', to='core.order')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_disputes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DisputeUpdate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_status', models.CharField(blank=True, choices=[('open', 'Open'), ('under_review', 'Under review'), ('resolved', 'Resolved'), ('rejected', 'Rejected')], max_length=20)),
                ('to_status', models.CharField(choices=[('open', 'Open'), ('under_review', 'Under review'), ('resolved', 'Resolved'), ('rejected', 'Rejected')], max_length=20)),
                ('response', models.TextField(blank=True, max_length=4000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('dispute', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='history', to='core.dispute')),
            ],
            options={
                'ordering': ['created_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='dispute',
            constraint=models.UniqueConstraint(condition=models.Q(('status__in', ['open', 'under_review'])), fields=('order',), name='one_active_dispute_per_order'),
        ),
    ]
