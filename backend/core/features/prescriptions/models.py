from django.db import models
from core.common.models import TimestampedModel


class Prescription(TimestampedModel):

    # Possible prescription statuses
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        COMPLETED = "completed", "Completed"

    # Types of prescriptions
    class Kind(models.TextChoices):
        SINGLE = "single_use", "Single Use"
        REPEAT = "repeat", "Repeat"

    # Patient and prescription information
    patient = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="prescriptions"
    )

    medication_name = models.CharField(max_length=255)
    doctor_name = models.CharField(max_length=180)
    issue_date = models.DateField()
    expiry_date = models.DateField()

    # Uploaded prescription document
    file = models.FileField(upload_to="prescriptions/%Y/%m/")

    # Prescription status and type
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )

    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        blank=True
    )

    refills_remaining = models.PositiveIntegerField(default=0)

    # Information about the person reviewing the prescription
    reviewed_by = models.ForeignKey(
        "core.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_prescriptions"
    )

    review_notes = models.TextField(blank=True)

    # Pharmacy where the prescription was used
    voided_at_pharmacy = models.ForeignKey(
        "core.Pharmacy",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    voided_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Check whether the prescription has been voided
    @property
    def is_voided(self):
        return self.voided_at is not None

    class Meta:
        db_table = "prescriptions_prescription"
