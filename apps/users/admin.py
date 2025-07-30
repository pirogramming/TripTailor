from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User  # 너의 커스텀 User 모델 import

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    pass
