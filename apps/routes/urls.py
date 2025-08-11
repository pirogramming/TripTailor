from django.urls import path
from . import views

urlpatterns = [
    path("<int:route_id>/", views.route_detail, name="route_detail"),
    path("<int:route_id>/add/<int:place_id>/", views.add_place, name="add_place"),
]