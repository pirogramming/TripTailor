from django.db import models
from apps.tags.models import Tag

class Place(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    region = models.CharField(max_length=100) # 필터링 주소(ex. 서울, 부산)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    external_id = models.CharField(max_length=100, blank=True, null=True) # 외부 API 지도 ID
    is_unique = models.BooleanField(default=False)
    summary = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='places')

    def __str__(self):
        return self.name
