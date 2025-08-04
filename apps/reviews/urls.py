# apps/reviews/urls.py
from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('', views.ReviewListView.as_view(), name='list'),
    path('<int:pk>/', views.ReviewDetailView.as_view(), name='detail'),
    path('create/', views.ReviewCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', views.ReviewUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', views.ReviewDeleteView.as_view(), name='delete'),
]
