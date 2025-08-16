# apps/routes/views.py
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Max, Q
from django.core.paginator import Paginator
from django.urls import reverse

from .models import Route, RoutePlace
from apps.places.models import Place

@login_required
@require_GET
def my_routes_json(request):
    """내 루트 목록을 (id, title)만 JSON으로 반환"""
    qs = Route.objects.filter(creator=request.user).order_by("-created_at")
    data = [{"id": r.id, "title": r.title} for r in qs]
    return JsonResponse({"routes": data})

@login_required
@require_POST
def create_route(request):
    title = (request.POST.get("title") or "").strip()
    if not title:
        return JsonResponse({"ok": False, "error": "title_required"}, status=400)

    location_summary = (request.POST.get("location_summary") or "").strip()  # ✅

    # (선택) 길이 검증
    if len(location_summary) > 200:
        return JsonResponse({"ok": False, "error": "summary_too_long"}, status=400)

    is_public = request.POST.get("is_public") == "true"

    route = Route.objects.create(
        creator=request.user,
        title=title,
        description=request.POST.get("description", "").strip(),
        cover_photo_url=request.POST.get("cover_photo_url", "").strip(),
        location_summary=location_summary,
        is_public=is_public,  # ✅ 저장
    )
    return JsonResponse({"ok": True, "route": {"id": route.id, "title": route.title}})


@login_required
@require_POST
def add_place(request, route_id: int, place_id: int):
    """선택한 내 루트에 장소 추가 (멱등)"""
    route = get_object_or_404(Route, pk=route_id, creator=request.user)
    place = get_object_or_404(Place, pk=place_id)

    # 이미 있으면 ok=True로 응답
    if RoutePlace.objects.filter(route=route, place=place).exists():
        return JsonResponse({"ok": True, "duplicated": True})

    with transaction.atomic():
        next_order = (RoutePlace.objects.filter(route=route).aggregate(m=Max("stop_order"))["m"] or 0) + 1
        RoutePlace.objects.create(route=route, place=place, stop_order=next_order)

    return JsonResponse({"ok": True, "duplicated": False, "order": next_order})

# (선택) 스탑 삭제 + 순번 압축
@login_required
@require_POST
def remove_place(request, route_id: int, place_id: int):
    route = get_object_or_404(Route, pk=route_id, creator=request.user)
    RoutePlace.objects.filter(route=route, place_id=place_id).delete()

    # 순번 1..N으로 압축
    with transaction.atomic():
        for i, rp in enumerate(
            RoutePlace.objects.filter(route=route).order_by("stop_order"),
            start=1
        ):
            if rp.stop_order != i:
                rp.stop_order = i
                rp.save(update_fields=["stop_order"])

    # AJAX/일반 모두 고려
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    from_page = request.GET.get("from") or request.POST.get("from") or ""
    edit_url = reverse("routes:edit_route_page", args=[route.id])
    return redirect(f"{edit_url}?from={from_page}") if from_page else redirect(edit_url)

def route_list(request):
    routes = Route.objects.filter(is_public=True).order_by('-created_at')
    paginator = Paginator(routes, 10)  # 한 페이지에 10개씩
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'routes/route_list.html', {'routes': page_obj})

def place_routes(request, place_id):
    from apps.places.models import Place
    place = get_object_or_404(Place, pk=place_id)
    routes = Route.objects.filter(stops__place_id=place.id).distinct().order_by('-created_at')
    paginator = Paginator(routes, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'routes/place_routes.html', {'routes': page_obj, 'place': place})

@login_required
def create_route_page(request):
    return render(request, "routes/create_route.html")

@login_required
def edit_route_page(request, route_id):
    route = get_object_or_404(Route, pk=route_id, creator=request.user)

    stops = (
        RoutePlace.objects
        .filter(route=route)
        .select_related("place")
        .order_by("stop_order")
    )

    from_page = request.GET.get("from", "")
    if not from_page:
        # Referer 기반 추론(선택)
        ref = (request.META.get("HTTP_REFERER") or "").lower()
        if "/users/mypage" in ref:
            from_page = "mypage"
        elif "/routes/" in ref and "public" in ref:  # 너네 공개목록 경로에 맞게 조건 조정
            from_page = "public_list"

    return render(request, "routes/edit_route.html", {
        "route": route,
        "from_page": from_page,
        "stops": stops,
    })

@login_required
@require_POST
def update_route(request, route_id):
    route = get_object_or_404(Route, pk=route_id, creator=request.user)

    # 1️⃣ 루트 정보 저장
    route.title = request.POST.get("title", "").strip()
    route.location_summary = request.POST.get("location_summary", "").strip()
    route.description = request.POST.get("description", "").strip()
    route.cover_photo_url = request.POST.get("cover_photo_url", "").strip()
    route.is_public = request.POST.get("is_public") == "true"
    route.save()

    # 2️⃣ 장소 순서 처리 (place_ids_json이 존재할 경우)
    place_ids_json = request.POST.get("place_ids_json")
    if place_ids_json:
        try:
            import json
            place_ids = json.loads(place_ids_json)

            with transaction.atomic():
                # 중복 방지를 위해 임시로 큰 수로 업데이트
                for i, place_id in enumerate(place_ids):
                    RoutePlace.objects.filter(route=route, place_id=place_id).update(stop_order=10000 + i)

                # 실제 순서대로 저장
                for i, place_id in enumerate(place_ids, start=1):
                    RoutePlace.objects.filter(route=route, place_id=place_id).update(stop_order=i)

        except Exception as e:
            return JsonResponse({"ok": False, "error": f"장소 순서 저장 실패: {str(e)}"}, status=400)

    # --- 리다이렉트: 상세페이지 없이 분기 ---
    from_page = (request.POST.get("from") or "").strip()
    if from_page == "mypage":
        return redirect(f"{reverse('users:my_page')}?tab=routes")
    if from_page == "public_list":
        return redirect("routes:route_list")

    # 기본값(안전한 경로): 공개 루트 목록
    return redirect("routes:route_list")

@login_required
@require_http_methods(["GET", "POST"])  
def delete_route(request, route_id):
    route = get_object_or_404(Route, pk=route_id, creator=request.user)
    route.delete()

    # 어디서 왔는지 확인
    from_page = request.GET.get("from", "")

    if from_page == "mypage":
         redirect_url = f"{reverse('users:my_page')}?tab=routes"
    elif from_page == "public_list":
        redirect_url = reverse("routes:route_list")
    else:
        redirect_url = "/routes/"

    if request.method == "GET":
        return redirect(redirect_url)
    else:
        return JsonResponse({"ok": True, "redirect_url": redirect_url})