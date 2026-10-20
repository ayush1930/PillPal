from django.db import models
from core.common.models import TimestampedModel

class InventoryItem(TimestampedModel):
    pharmacy = models.ForeignKey('core.Pharmacy', on_delete=models.CASCADE, related_name='inventory')
    medication = models.ForeignKey('core.Medication', on_delete=models.PROTECT, related_name='inventory_items')
    supplier = models.ForeignKey('core.Supplier', null=True, blank=True, on_delete=models.SET_NULL)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'inventory_inventoryitem'
        unique_together = ('pharmacy', 'medication')

class ReorderRequest(TimestampedModel):

    class Status(models.TextChoices):
        PENDING = ('pending', 'Pending')
        APPROVED = ('approved', 'Approved')
        SENT = ('sent', 'Sent')
        RECEIVED = ('received', 'Received')
        CANCELLED = ('cancelled', 'Cancelled')
    inventory_item = models.ForeignKey('core.InventoryItem', on_delete=models.PROTECT, related_name='reorders')
    requested_by = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='reorders')
    quantity = models.PositiveIntegerField()
    priority = models.CharField(max_length=20, default='normal')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'inventory_reorderrequest'
