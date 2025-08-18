from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from apps.places.models import PlaceLike, Place
from django.db.models import Count, Prefetch
from django.db.models import prefetch_related_objects
from apps.routes.models import Route, RoutePlace
from apps.reviews.models import Review

from django.contrib.auth.views import PasswordResetView
from django.contrib import messages
from django.urls import reverse_lazy
from .forms import CustomPasswordResetForm
from django.contrib.auth import get_user_model


def login_page(request):
    return render(request, 'users/login.html')

def main_page(request):
    # 로그인된 사용자만 데이터 표시
    if request.user.is_authenticated:
        return my_page(request)
    else:
        # 로그인되지 않은 경우 로그인 페이지로 리다이렉트
        return redirect('users:login_page')

@login_required
def my_page(request):
    tab = request.GET.get("tab", "likes")
    ctx = {"tab": tab}

    if tab == "likes":
        ctx["items"] = PlaceLike.objects.filter(user=request.user).order_by("-created_at")[:30]
    elif tab == "routes":
        ctx["items"] = Route.objects.filter(creator=request.user).order_by("-created_at")[:30]
    elif tab == "reviews":
        ctx["items"] = Review.objects.filter(user=request.user).order_by("-created_at")[:30]


    # --- 좋아요한 장소
    likes_qs = (
        PlaceLike.objects
        .filter(user=request.user)
        .select_related("place")
        .prefetch_related("place__tags")
        .order_by("-created_at")
    )
    likes_paginator = Paginator(likes_qs, 6)
    likes_page = likes_paginator.get_page(request.GET.get("page_likes", 1))
    total_likes = likes_qs.count()

    for lk in likes_page.object_list:
        # lk는 PlaceLike, lk.place는 select_related로 미리 붙어 있음
        lk.place.is_liked = True

    # --- 내가 만든 루트
    routes_qs = (
        Route.objects
        .filter(creator=request.user)
        .annotate(num_stops=Count("stops"))
        .order_by("-created_at")
    )
    routes_paginator = Paginator(routes_qs, 6)
    routes_page = routes_paginator.get_page(request.GET.get("page_routes", 1))
    total_routes = routes_qs.count()

    # --- 내가 작성한 리뷰 (내용이 있는 것만)
    reviews_qs = (
        Review.objects
        .filter(user=request.user, content__isnull=False).exclude(content='')  # 내용이 있는 리뷰만
        .select_related("place")
        .prefetch_related("photos")
        .order_by("-created_at")
    )
    reviews_paginator = Paginator(reviews_qs, 6)
    reviews_page = reviews_paginator.get_page(request.GET.get("page_reviews", 1))
    total_reviews = reviews_qs.count()

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

    return render(request, "users/mypage.html",{
        "tab": tab,
        
        # 좋아요 섹션
        "likes_page": likes_page,
        "total_likes": total_likes,

        # 루트 섹션
        "routes_page": routes_page,
        "routes_total": total_routes,

        # 리뷰 섹션
        "reviews_page": reviews_page,
        "total_reviews": total_reviews,
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

class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm
    template_name = 'account/password_reset.html'
    success_url = reverse_lazy("users:password_reset_done")
    def form_valid(self, form):
        messages.success(self.request, "비밀번호 재설정 메일을 보냈어요. 메일함을 확인해 주세요.")
        return super().form_valid(form)


@login_required
def delete_review_ajax(request, place_id, review_id):
    """AJAX로 댓글을 바로 삭제하는 뷰"""
    if request.method == 'POST':
        try:
            review = get_object_or_404(Review, pk=review_id, user=request.user)
            review.delete()
            return JsonResponse({'success': True, 'message': '댓글이 삭제되었습니다.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'삭제 중 오류가 발생했습니다: {str(e)}'})
    
    return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'})