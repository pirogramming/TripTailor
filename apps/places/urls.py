from django.urls import path
from . import views

app_name = 'places'

urlpatterns = [
    path('', views.main, name='main'),  # 메인 화면
    path('search/', views.search, name='search'), 
    path('place-search/', views.place_search, name='place_search'),  # 새로운 장소 검색 화면
    path('<int:pk>/', views.place_detail, name='place_detail'),
    path('<int:pk>/like/', views.toggle_place_like, name='place_like'),
    path('fragment/', views.place_list_fragment, name='place_list_fragment'),
]