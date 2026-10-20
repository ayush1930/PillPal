"""Record in-person cash collection. No online payment gateway is used."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from core.features.orders.models import Order


@transaction.atomic
def record_cash_payment(*, order_id, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    permitted = actor.role == 'admin' or (
        actor.role == 'pharmacist' and order.pharmacy.staff.filter(user=actor).exists()
    ) or (actor.role == 'driver' and order.driver_id == actor.pk and order.delivery_type == 'delivery')
    if not permitted:
        raise PermissionDenied
    if order.status != 'delivered':
        raise ValidationError('Complete the delivery or pickup before recording cash collection.')
    if order.payment_reference and order.payment_reference != 'cash:collected':
        raise ValidationError('This order already has a different payment reference.')
    order.payment_reference = 'cash:collected'
    order.save(update_fields=['payment_reference', 'updated_at'])
    return order
