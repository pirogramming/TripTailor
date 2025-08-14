from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.users.models import User
from apps.routes.models import Route
from apps.places.models import Place


class Review(models.Model):
    user = models.ForeignKey(User, related_name="reviews", on_delete=models.CASCADE)

    # Place는 필수 입력 항목 (장소 기반 댓글)
    place = models.ForeignKey(
        Place,
        related_name="reviews",
        on_delete=models.CASCADE,
        verbose_name="장소",
    )

    # 0.5 단위로 입력
    rating = models.DecimalField(
        max_digits=2,
        decimal_places=1,
        validators=[
            MinValueValidator(Decimal("0.0")),
            MaxValueValidator(Decimal("5.0")),
        ],
        help_text="0.0 ~ 5.0 (0.5 단위)",
    )

    content = models.TextField()
    summary = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-created_at"]  # 리스트뷰 페이지네이션 경고 방지용


class ReviewPhoto(models.Model):
    review = models.ForeignKey(Review, related_name="photos", on_delete=models.CASCADE)
    url = models.URLField(blank=True, null=True, verbose_name="사진 URL")

    def __str__(self):
        return f"Photo of {self.review_id}"