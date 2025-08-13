from django.urls import path
from . import views

app_name = 'places'

urlpatterns = [
    path('', views.main, name='main'),  # 메인 화면
    path('search/', views.search, name='search'), 
    path('more-recommendations/', views.more_recommendations, name='more_recommendations'),
    path('more-recommendations-ajax/', views.more_recommendations_ajax, name='more_recommendations_ajax'),
    path('<int:pk>/', views.place_detail, name='place_detail'),
    path('<int:pk>/like/', views.toggle_place_like, name='place_like'),
    path("tags-json/", views.tags_json, name="tags_json"),
    
    # 벡터 검색 API 엔드포인트
    path('api/vector-search/', views.vector_search_api, name='vector_search_api'),
    path('api/update-embeddings/', views.update_embeddings_api, name='update_embeddings_api'),
]