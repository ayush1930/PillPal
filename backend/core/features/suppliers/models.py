from django.db import models
from core.common.models import TimestampedModel

class Supplier(TimestampedModel):
    name = models.CharField(max_length=180)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    lead_time_days = models.PositiveIntegerField(default=5)
    payment_terms = models.CharField(max_length=80, default='Net 30')
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'suppliers_supplier'
