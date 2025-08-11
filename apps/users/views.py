from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from apps.places.models import PlaceLike
from django.db.models import Count, Prefetch
from django.db.models import prefetch_related_objects
from apps.routes.models import Route, RoutePlace
from apps.reviews.models import Review

def login_page(request):
    return render(request, 'users/login.html')

def main_page(request):
    return render(request, 'users/mypage.html')

@login_required
def my_page(request):
    likes_qs = (
        PlaceLike.objects
        .filter(user=request.user)
        .select_related("place")
        .prefetch_related("place__tags")
        .order_by("-created_at")
    )
    likes_paginator = Paginator(likes_qs, 5)
    likes_page = likes_paginator.get_page(request.GET.get("page"))  # 기존: page
    total_likes = likes_qs.count()

    # --- 내가 만든 루트
    routes_qs = (
        Route.objects
        .filter(creator=request.user)
        .annotate(num_stops=Count("stops"))              # 스탑 개수
        .order_by("-created_at")
    )
    routes_paginator = Paginator(routes_qs, 5)          # 루트는 5개씩
    routes_page = routes_paginator.get_page(request.GET.get("page_routes"))  # 새 파라미터
    total_routes = routes_qs.count()

    # 현재 페이지에 뜨는 루트들만 스탑 미리 가져오기(미리보기)
    preview_qs = (
        RoutePlace.objects
        .select_related("place")
        .order_by("stop_order")
    )
    routes_on_page = list(routes_page.object_list)
    if routes_on_page:
        prefetch_related_objects(
            routes_on_page,
            Prefetch("stops", queryset=preview_qs, to_attr="prefetched_stops"),
        )

    return render(request, "users/mypage.html", {
        # 좋아요 섹션(기존 이름 유지)
        "page_obj": likes_page,
        "total": total_likes,

        # 루트 섹션(추가)
        "routes_page": routes_page,
        "routes_total": total_routes,
    })

@login_required
def my_reviews(request):
    reviews_qs = (
        Review.objects
        .filter(user=request.user)
        .prefetch_related("photos")  # 리뷰 사진 미리 로드
        .order_by("-created_at")
    )

    paginator = Paginator(reviews_qs, 5)  # 페이지당 5개
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "users/my_reviews.html", {
        "page_obj": page_obj,
        "total": reviews_qs.count(),
    })
