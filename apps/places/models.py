from django.db import models
from apps.tags.models import Tag
from apps.users.models import User

class Place(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    region = models.CharField(max_length=100) # 필터링 주소(ex. 서울, 부산)
    overview = models.TextField(blank=True, null=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    external_id = models.CharField(max_length=100, blank=True, null=True) # 외부 API 지도 ID
    is_unique = models.BooleanField(default=False)
    summary = models.TextField(blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='places')
    place_class = models.IntegerField(default=0)  # class 필드 추가 (1: 레포츠, 2: 쇼핑, 3: 관광지, 4: 문화시설)

    def __str__(self):
        return self.name

class PlaceLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    place = models.ForeignKey(Place, on_delete=models.CASCADE, related_name='placelikes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'place')
    def __str__(self):
        return f"{self.user} likes {self.place}"