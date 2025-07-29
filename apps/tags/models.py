from django.db import models
from apps.routes.models import Route

class Tag(models.Model):
    name = models.CharField(max_length=50)
    tag_type = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.name

class RouteTag(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta: # 루트와 태그 쌍은 유일.
        constraints = [
            models.UniqueConstraint(fields=["route", "tag"], name="unique_route_tag")
        ]
