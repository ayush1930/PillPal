from django.core.validators import MinValueValidator
from django.db import models, transaction
from core.common.models import TimestampedModel

class Order(TimestampedModel):

    class Status(models.TextChoices):
        PENDING = ('pending', 'Pending')
        PROCESSING = ('processing', 'Processing')
        READY = ('ready', 'Ready')
        OUT_FOR_DELIVERY = ('out_for_delivery', 'Out for Delivery')
        DELIVERED = ('delivered', 'Delivered')
        CANCELLED = ('cancelled', 'Cancelled')

    class DeliveryType(models.TextChoices):
        DELIVERY = ('delivery', 'Delivery')
        PICKUP = ('pickup', 'Pickup')
    patient = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='orders')
    pharmacy = models.ForeignKey('core.Pharmacy', on_delete=models.PROTECT, related_name='orders')
    prescription = models.ForeignKey('core.Prescription', null=True, blank=True, on_delete=models.PROTECT, related_name='orders')
    driver = models.ForeignKey('core.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='deliveries')
    delivery_address = models.ForeignKey('core.Address', null=True, blank=True, on_delete=models.PROTECT)
    delivery_type = models.CharField(max_length=20, choices=DeliveryType.choices)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_reference = models.CharField(max_length=255, blank=True)
    estimated_delivery = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    proof_of_delivery = models.ImageField(upload_to='delivery-proofs/%Y/%m/', blank=True)

    @property
    def cash_collected(self):
        return self.payment_reference == 'cash:collected'

    def mark_delivered(self):
        from core.features.prescriptions.models import Prescription
        from django.core.exceptions import ValidationError
        from django.db.models import F
        from django.utils import timezone
        with transaction.atomic():
            now = timezone.now()
            expected = self.Status.READY if self.delivery_type == 'pickup' else self.Status.OUT_FOR_DELIVERY
            if not Order.objects.filter(pk=self.pk, status=expected).update(
                    status=self.Status.DELIVERED, delivered_at=now, updated_at=now):
                raise ValidationError('This order is not ready to be completed.')
            if self.prescription_id:
                prescription = Prescription.objects.select_for_update().get(pk=self.prescription_id)
                if prescription.kind == Prescription.Kind.SINGLE:
                    prescription.voided_at = now
                    prescription.voided_at_pharmacy = self.pharmacy
                    prescription.status = Prescription.Status.COMPLETED
                    prescription.save(update_fields=['voided_at', 'voided_at_pharmacy', 'status', 'updated_at'])
                elif prescription.kind == Prescription.Kind.REPEAT:
                    if not Prescription.objects.filter(pk=prescription.pk, refills_remaining__gt=0).update(
                            refills_remaining=F('refills_remaining') - 1, updated_at=now):
                        raise ValidationError('This prescription has no available refills.')
            self.refresh_from_db()

    class Meta:
        db_table = 'orders_order'

class OrderItem(models.Model):
    order = models.ForeignKey('core.Order', on_delete=models.CASCADE, related_name='items')
    inventory_item = models.ForeignKey('core.InventoryItem', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'orders_orderitem'
