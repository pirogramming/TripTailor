# apps/reviews/urls.py
from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    # Place 기반 댓글 CRUD URL들
    path('place/<int:place_id>/create/', views.PlaceReviewCreateView.as_view(), name='place_create'),
    path('place/<int:place_id>/<int:pk>/edit/', views.PlaceReviewUpdateView.as_view(), name='place_edit'),
    
    # AJAX 삭제
    path('place/<int:place_id>/<int:review_id>/delete/', views.delete_review_ajax, name='delete_review_ajax'),
    
    # HTMX 댓글 목록
    path('htmx/<int:place_id>/', views.place_review_list_htmx, name='htmx_list'),
    path("blogs/<int:place_id>/", views.blog_reviews, name="blog_reviews"),
]
