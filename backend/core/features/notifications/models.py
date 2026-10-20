from django.db import models
from core.common.models import TimestampedModel

class Notification(TimestampedModel):
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=180)
    body = models.TextField()
    link = models.CharField(max_length=120, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'notifications_notification'
