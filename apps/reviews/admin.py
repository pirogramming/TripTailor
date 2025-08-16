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
    list_display = ('id','user', 'rating','created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('content', 'user__username')
    inlines = [ReviewPhotoInline]

@admin.register(ReviewPhoto)
class ReviewPhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'review', 'image')
    search_fields = ('image',)
