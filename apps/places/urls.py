from django.urls import path
from . import views

app_name = 'places'

urlpatterns = [
    path('', views.main, name='main'),  # 메인 화면
    # 필요하다면 상세 페이지 등 추가
    # path('<int:pk>/', views.place_detail, name='place_detail'),
]