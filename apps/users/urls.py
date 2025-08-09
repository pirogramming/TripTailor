from django.urls import path
from . import views
from .views import main_page

app_name = 'users'

urlpatterns = [
    path('login/', views.login_page, name='login_page'),
    path('', main_page, name='main_page'),  # ✅ /
    path('main/', main_page, name='main_page'),
]
