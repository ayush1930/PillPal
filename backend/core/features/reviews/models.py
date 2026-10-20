from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from core.common.models import TimestampedModel

class Review(TimestampedModel):
    patient = models.ForeignKey('core.User', on_delete=models.CASCADE, related_name='reviews')
    pharmacy = models.ForeignKey('core.Pharmacy', on_delete=models.CASCADE, related_name='reviews')
    order = models.OneToOneField('core.Order', on_delete=models.CASCADE, related_name='review')
    driver = models.ForeignKey('core.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='driver_reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)

    class Meta:
        db_table = 'reviews_review'
