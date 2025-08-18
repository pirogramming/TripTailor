# apps/users/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

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
     path('password/reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='account/password_reset_done.html'
    ), name='password_reset_done'),

    path('password/reset/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(),
        template_name="admin/password_reset_confirm.html",
        name='password_reset_confirm',
    ),

    path('password/reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='admin/password_reset_complete.html'
    ), name='password_reset_complete'),
]
