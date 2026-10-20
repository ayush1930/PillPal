from django.db import models
from core.common.models import TimestampedModel

class Medication(TimestampedModel):
    name = models.CharField(max_length=180)
    generic_name = models.CharField(max_length=180)
    brand = models.CharField(max_length=180, blank=True)
    category = models.CharField(max_length=120)
    dosage_form = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    requires_prescription = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'medications_medication'
