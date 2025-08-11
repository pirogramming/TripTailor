from django.db import models
from apps.users.models import User

class Route(models.Model):
    creator = models.ForeignKey(User, related_name="routes", on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    cover_photo_url = models.URLField()
    location_summary = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class RoutePlace(models.Model):
    from apps.places.models import Place

    route = models.ForeignKey(Route, related_name="stops", on_delete=models.CASCADE)
    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    stop_order = models.PositiveSmallIntegerField() # 방문 순서
    tip = models.TextField(blank=True) 

    class Meta:
        unique_together = (("route", "stop_order"), ("route", "place"))
        ordering = ["stop_order"]

class SavedRoute(models.Model): # 찜한 루트
    user = models.ForeignKey(User, related_name="saved_routes", on_delete=models.CASCADE)
    route = models.ForeignKey(Route, related_name="saved_by_users", on_delete=models.CASCADE)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "route")