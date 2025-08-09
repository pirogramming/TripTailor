from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.login_page, name='login_page'),
    path('', views.main_page, name='main_page'),  # ✅ /
    path('main/', views.main_page, name='main_page'),
]
