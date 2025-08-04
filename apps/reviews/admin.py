from django.contrib import admin

# Register your models here.
# apps/reviews/admin.py
from django.contrib import admin
from .models import Review, ReviewPhoto

class ReviewPhotoInline(admin.TabularInline):
    model = ReviewPhoto
    extra = 1

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'route', 'user', 'rating', 'summary', 'created_at')
    list_filter = ('route', 'rating', 'created_at')
    search_fields = ('summary', 'content', 'user__username', 'route__name')
    inlines = [ReviewPhotoInline]

@admin.register(ReviewPhoto)
class ReviewPhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'review', 'url')
    search_fields = ('url',)
