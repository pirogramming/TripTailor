from django.contrib import admin
from .models import Route, RoutePlace, SavedRoute


# --- Inlines ---
class RoutePlaceInline(admin.TabularInline):
    model = RoutePlace
    extra = 1
    fields = ("stop_order", "place", "tip")
    ordering = ("stop_order",)
    raw_id_fields = ("place",)  # Place가 많을 수 있으니 성능 최적화


# --- Route ---
@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "creator",
        "location_summary",
        "created_at",
        "updated_at",
        "stops_count",
        "saved_count",
    )
    list_filter = ("created_at", "updated_at")
    search_fields = (
        "title",
        "location_summary",
        "creator__username",
        "creator__email",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("creator",)
    readonly_fields = ("created_at", "updated_at")

    inlines = [RoutePlaceInline]

    def stops_count(self, obj):
        return obj.stops.count()
    stops_count.short_description = "정차 수"

    def saved_count(self, obj):
        return obj.saved_by_users.count()
    saved_count.short_description = "찜 수"


# --- RoutePlace ---
@admin.register(RoutePlace)
class RoutePlaceAdmin(admin.ModelAdmin):
    list_display = ("id", "route", "stop_order", "place_name", "region", "tip_short")
    list_filter = ("route", "place__region")
    search_fields = (
        "route__title",
        "place__name",
        "place__address",
        "place__region",
    )
    ordering = ("route", "stop_order")
    raw_id_fields = ("route", "place")
    list_select_related = ("route", "place")

    def place_name(self, obj):
        return obj.place.name
    place_name.short_description = "장소 이름"

    def region(self, obj):
        return obj.place.region
    region.short_description = "지역"

    def tip_short(self, obj):
        return (obj.tip[:30] + "…") if obj.tip and len(obj.tip) > 30 else obj.tip
    tip_short.short_description = "팁 요약"


# --- SavedRoute ---
@admin.register(SavedRoute)
class SavedRouteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "route", "saved_at")
    list_filter = ("saved_at",)
    search_fields = ("user__username", "user__email", "route__title")
    date_hierarchy = "saved_at"
    ordering = ("-saved_at",)
    raw_id_fields = ("user", "route")
    list_select_related = ("user", "route")
