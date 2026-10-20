
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.common.models import TimestampedModel


class Pharmacy(TimestampedModel):
    # Basic pharmacy information
    name = models.CharField(max_length=180)
    address = models.TextField()
    phone = models.CharField(max_length=40)
    email = models.EmailField(blank=True)

    # Pharmacy location
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )

    # Opening hours and delivery information
    opening_hours = models.JSONField(default=dict)
    delivery_available = models.BooleanField(default=True)
    delivery_radius_miles = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10
    )

    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "pharmacies_pharmacy"


class PharmacyStaff(models.Model):
    # Connects staff members to a pharmacy
    pharmacy = models.ForeignKey(
        "core.Pharmacy",
        on_delete=models.CASCADE,
        related_name="staff"
    )

    user = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="pharmacy_memberships"
    )

    is_manager = models.BooleanField(default=False)

    class Meta:
        db_table = "pharmacies_pharmacystaff"
        unique_together = ("pharmacy", "user")
