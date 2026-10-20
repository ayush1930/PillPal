from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.features.inventory.models import InventoryItem
from core.features.notifications.models import Notification
from core.features.orders.models import Order, OrderItem
from core.features.prescriptions.models import Prescription


def _staff_for(actor, order):
    return actor.role == 'admin' or (
        actor.role == 'pharmacist' and order.pharmacy.staff.filter(user=actor).exists()
    )

def _notify(order, title):
    Notification.objects.create(user=order.patient, kind='order', title=title,
                                body=f'Order #{order.pk}: {order.get_status_display()}.')


@transaction.atomic
def place_order(*, patient, cart, delivery_type, address=None, prescription=None):
    if not patient.is_active or patient.role != 'patient':
        raise PermissionDenied
    if delivery_type not in Order.DeliveryType.values:
        raise ValidationError('Choose delivery or pickup.')
    if not cart:
        raise ValidationError('Your cart is empty.')
    quantities = {}
    try:
        for key, value in cart.items():
            if isinstance(value, bool) or int(value) != value or int(value) < 1:
                raise ValueError
            quantities[int(key)] = int(value)
    except (TypeError, ValueError):
        raise ValidationError('Choose whole, positive quantities.')
    stock = list(InventoryItem.objects.select_for_update().filter(
        pk__in=quantities, active=True, medication__active=True, pharmacy__active=True
    ).select_related('medication', 'pharmacy').order_by('pk'))
    if len(stock) != len(quantities):
        raise ValidationError('One or more cart items are no longer available.')
    if len({item.pharmacy_id for item in stock}) != 1:
        raise ValidationError('Choose items from one pharmacy.')
    pharmacy = stock[0].pharmacy
    if delivery_type == 'delivery':
        if not address or address.user_id != patient.pk:
            raise ValidationError('Choose your own delivery address.')
        if not pharmacy.delivery_available:
            raise ValidationError('This pharmacy offers pickup only.')
    else:
        address = None
    if prescription:
        prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)
        if (prescription.patient_id != patient.pk or prescription.deleted_at or
            prescription.status != 'approved' or prescription.is_voided or
            prescription.expiry_date < timezone.localdate() or
            prescription.kind not in Prescription.Kind.values):
            raise ValidationError('Choose a valid approved prescription.')
        if prescription.kind == 'repeat' and prescription.refills_remaining < 1:
            raise ValidationError('This prescription has no available refills.')
        if prescription.orders.exclude(status__in=['delivered', 'cancelled']).exists():
            raise ValidationError('This prescription already has an active order.')
    if any(item.medication.requires_prescription for item in stock) and not prescription:
        raise ValidationError('A prescription is required for these medications.')
    subtotal = sum((item.price * quantities[item.pk] for item in stock), Decimal('0'))
    if any(item.price < 0 for item in stock):
        raise ValidationError('A medication price is invalid; contact the pharmacy.')
    fee = Decimal('4.99') if delivery_type == 'delivery' and subtotal < 30 else Decimal('0')
    order = Order.objects.create(patient=patient, pharmacy=pharmacy, prescription=prescription,
        delivery_address=address, delivery_type=delivery_type, subtotal=subtotal,
        delivery_fee=fee, tax=0, total=subtotal + fee)
    for item in stock:
        quantity = quantities[item.pk]
        # Conditional update protects stock even on SQLite, which has no row-level SELECT lock.
        changed = InventoryItem.objects.filter(pk=item.pk, stock__gte=quantity).update(
            stock=F('stock') - quantity, updated_at=timezone.now())
        if not changed:
            raise ValidationError(f'Insufficient stock for {item.medication.name}.')
        OrderItem.objects.create(order=order, inventory_item=item, quantity=quantity, unit_price=item.price)
    _notify(order, 'Order placed')
    return order


@transaction.atomic
def accept_delivery(*, order_id, actor):
    if actor.role not in ['driver', 'admin']:
        raise PermissionDenied
    changed = Order.objects.filter(pk=order_id, status='ready', driver__isnull=True,
                                   delivery_type='delivery').update(
        driver=actor, status='out_for_delivery', updated_at=timezone.now())
    if not changed:
        raise ValidationError('This delivery is no longer available.')
    order = Order.objects.get(pk=order_id)
    _notify(order, 'Your order is out for delivery')
    return order


@transaction.atomic
def complete_order(*, order_id, actor, proof=None):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.delivery_type == 'pickup':
        permitted = _staff_for(actor, order)
        expected = 'ready'
    else:
        permitted = actor.role == 'admin' or (actor.role == 'driver' and order.driver_id == actor.pk)
        expected = 'out_for_delivery'
    if not permitted:
        raise PermissionDenied
    if order.status != expected:
        raise ValidationError('This order is not ready to be completed.')
    if proof:
        from django import forms
        proof = forms.ImageField().clean(proof)
        order.proof_of_delivery = proof
        order.save(update_fields=['proof_of_delivery'])
    order.mark_delivered()
    _notify(order, 'Order completed')
    return order


@transaction.atomic
def change_order_status(*, order_id, actor, status):
    order = Order.objects.select_for_update().get(pk=order_id)
    if not _staff_for(actor, order):
        raise PermissionDenied
    allowed = {'pending': ['processing', 'cancelled'], 'processing': ['ready', 'cancelled'],
               'ready': ['cancelled']}
    if status not in allowed.get(order.status, []):
        raise ValidationError('Invalid order status transition.')
    # Conditional state change makes cancellation/restocking happen at most once.
    if not Order.objects.filter(pk=order.pk, status=order.status).update(status=status, updated_at=timezone.now()):
        raise ValidationError('The order has changed. Refresh and try again.')
    if status == 'cancelled':
        for item in order.items.all():
            InventoryItem.objects.filter(pk=item.inventory_item_id).update(
                stock=F('stock') + item.quantity, updated_at=timezone.now())
    order.refresh_from_db()
    _notify(order, 'Order status updated')
    return order
