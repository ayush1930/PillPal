from django.db import models
from core.common.models import TimestampedModel

class PaymentMethod(TimestampedModel):

    class Kind(models.TextChoices):
        CARD = ('card', 'Card')
        MOBILE_MONEY = ('mobile_money', 'Mobile Money')
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, related_name='payment_methods')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    provider = models.CharField(max_length=80)
    token = models.CharField(max_length=255)
    display_value = models.CharField(max_length=80)
    expiry = models.CharField(max_length=7, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = 'payments_paymentmethod'
