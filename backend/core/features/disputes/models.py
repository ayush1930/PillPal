from pathlib import Path
from uuid import uuid4

from django.db import models
from django.db.models import Q
from core.common.models import TimestampedModel


def evidence_path(instance, filename):
    return f'disputes/{instance.order_id}/{uuid4().hex}{Path(filename).suffix.lower()}'


class Dispute(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        UNDER_REVIEW = 'under_review', 'Under review'
        RESOLVED = 'resolved', 'Resolved'
        REJECTED = 'rejected', 'Rejected'

    class Category(models.TextChoices):
        ORDER = 'order', 'Order problem'
        DELIVERY = 'delivery', 'Delivery problem'
        MEDICATION = 'medication', 'Medication problem'
        PAYMENT = 'payment', 'Payment query'
        OTHER = 'other', 'Other'

    order = models.ForeignKey('core.Order', on_delete=models.PROTECT, related_name='disputes')
    subject = models.CharField(max_length=180)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField(max_length=4000)
    evidence = models.FileField(upload_to=evidence_path, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    admin_response = models.TextField(max_length=4000, blank=True)
    updated_by = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='reviewed_disputes')
    closed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['order'],
            condition=Q(status__in=['open', 'under_review']), name='one_active_dispute_per_order')]

    def __str__(self):
        return f'Dispute #{self.pk} — Order #{self.order_id}'


class DisputeUpdate(models.Model):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name='history')
    actor = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True)
    from_status = models.CharField(max_length=20, choices=Dispute.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Dispute.Status.choices)
    response = models.TextField(max_length=4000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
