from django.contrib import admin

# Register your models here.

from django.contrib import admin
from .models import Place

@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'region', 'address')
    search_fields = ('name', 'region', 'address')
