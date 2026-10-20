from django.db import models
from core.common.models import TimestampedModel


class Reminder(TimestampedModel):

    # Patient who created the reminder
    patient = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="reminders"
    )

    # Medication information
    medication_name = models.CharField(max_length=180)
    dosage = models.CharField(max_length=80)
    frequency = models.CharField(max_length=120)

    # Times when the patient should take the medication
    times = models.JSONField(default=list)

    # Reminder dates
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    # Whether the reminder is active
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "reminders_reminder"
