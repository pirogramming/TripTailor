from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from apps.places.models import PlaceLike

def login_page(request):
    return render(request, 'users/login.html')

def main_page(request):
    return render(request, 'users/mypage.html')

@login_required
def my_page(request):
    likes_qs = (
        PlaceLike.objects
        .filter(user = request.user)
        .select_related("place")
        .prefetch_related("place__tags")
        .order_by("-created_at")
    )

    paginator = Paginator(likes_qs, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "users/mypage.html", {
        "page_obj":page_obj,
        "total":likes_qs.count(),
    })
