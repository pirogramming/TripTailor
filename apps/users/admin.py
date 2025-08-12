from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Provider Info", {"fields": ("provider", "provider_uid", "joined_at")}),
    )
    readonly_fields = ("joined_at",)
    list_display = (
        "username",
        "email",
        "provider",
        "provider_uid",
        "is_staff",
        "is_active",
        "date_joined",
        "joined_at",
    )
    list_filter = ("provider", "is_staff", "is_superuser", "is_active")