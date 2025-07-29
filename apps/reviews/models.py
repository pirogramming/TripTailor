from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.users.models import User
from apps.routes.models import Route

class Review(models.Model):
    user = models.ForeignKey(User, related_name="reviews", on_delete=models.CASCADE)
    route = models.ForeignKey(Route, related_name="reviews", on_delete=models.CASCADE)
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        validators=[
            MinValueValidator(0.0),
            MaxValueValidator(5.0),
        ]
    )
    content = models.TextField()
    summary = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

class ReviewPhoto(models.Model):
    review = models.ForeignKey(Review, related_name="photos", on_delete=models.CASCADE)
    url = models.URLField()
