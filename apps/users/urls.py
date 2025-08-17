# apps/users/urls.py
from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.login_page, name='login_page'),
    path('', views.main_page, name='main_page'),
    path('main/', views.main_page, name='main_page'),
    path('mypage/', views.my_page, name='my_page'),

    # 비밀번호 재설정
    path(
        'password/reset/',
        views.CustomPasswordResetView.as_view(),  # ✅ 여기 확인!
        name='account_reset_password'
    ),
]
