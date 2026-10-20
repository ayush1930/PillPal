from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import InventoryItem, ReorderRequest


@transaction.atomic
def add_inventory(*, actor, pharmacy, supplier, price, quantity, reorder_level, medication=None, **details):
    from core.features.medications.models import Medication
    if actor.role != 'admin' and not (actor.role == 'pharmacist' and pharmacy.staff.filter(user=actor).exists()):
        raise PermissionDenied
    if isinstance(quantity, bool) or int(quantity) != quantity or quantity < 1 or price < 0 or not pharmacy.active:
        raise ValidationError('Choose active stock and positive quantities.')
    if reorder_level < 0 or (supplier and not supplier.active):
        raise ValidationError('Choose an active supplier and a valid reorder level.')
    if medication is not None:
        medication = Medication.objects.get(pk=medication.pk)
        if not medication.active:
            raise ValidationError('Choose an active medication.')
    else:
        medication = Medication(**details)
        medication.full_clean()
        medication.save()
    item, created = InventoryItem.objects.get_or_create(pharmacy=pharmacy, medication=medication,
        defaults=dict(supplier=supplier, price=price, stock=quantity, reorder_level=reorder_level))
    if not created:
        InventoryItem.objects.filter(pk=item.pk).update(stock=F('stock') + quantity,
            price=price, supplier=supplier, reorder_level=reorder_level, active=True, updated_at=timezone.now())
        item.refresh_from_db()
    return item


@transaction.atomic
def change_reorder_status(*, reorder_id, actor, status):
    reorder = ReorderRequest.objects.select_for_update().select_related('inventory_item__pharmacy').get(pk=reorder_id)
    if actor.role != 'admin' and not (
        actor.role == 'pharmacist' and reorder.inventory_item.pharmacy.staff.filter(user=actor).exists()
    ):
        raise PermissionDenied
    allowed = {'pending': ['approved', 'cancelled'], 'approved': ['sent', 'cancelled'], 'sent': ['received']}
    if status not in allowed.get(reorder.status, []):
        raise ValidationError('Invalid reorder status transition.')
    if not ReorderRequest.objects.filter(pk=reorder.pk, status=reorder.status).update(status=status, updated_at=timezone.now()):
        raise ValidationError('This reorder has changed. Refresh and try again.')
    if status == 'received':
        InventoryItem.objects.filter(pk=reorder.inventory_item_id).update(stock=F('stock') + reorder.quantity, updated_at=timezone.now())
    reorder.refresh_from_db()
    return reorder
