# apps/routes/urls.py
from django.urls import path
from . import views

app_name = "routes"

urlpatterns = [
    path("mine/json/", views.my_routes_json, name="my_routes_json"),
    path("create/", views.create_route, name="create_route"), #ajax관련 create
    path("create/page/", views.create_route_page, name="create_route_page"), #루트 생성 페이지
    path("<int:route_id>/add/<int:place_id>/", views.add_place, name="add_place"),

    # ✅ 루트 상세
    path("<int:route_id>/", views.route_detail, name="detail"),

    # (선택) 스탑 삭제 — 원하면 템플릿에서 버튼 활성화
    path("<int:route_id>/remove_place/<int:place_id>/", views.remove_place, name="remove_place"),
    path('', views.route_list, name='route_list'),
    path('place/<int:place_id>/', views.place_routes, name='place_routes'),

    path("<int:route_id>/edit/", views.edit_route_page, name="edit_route_page"),  # 수정 폼
    path("<int:route_id>/update/", views.update_route, name="update_route"),      # 수정 처리
    path("<int:route_id>/update_order/", views.update_place_order, name="update_place_order"), #장소 순서 처리
]
