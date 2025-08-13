# apps/routes/views.py
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction
from django.db.models import Max
from django.core.paginator import Paginator
from django.urls import reverse

from .models import Route, RoutePlace
from apps.places.models import Place

@login_required
def route_detail(request, route_id: int):
    """내 루트 상세: 스탑을 순서대로 나열"""
    from django.db.models import Q

    route = get_object_or_404(
    Route,
    Q(pk=route_id) & (Q(creator=request.user) | Q(is_public=True))  # ← 이렇게 전체 조건을 Q()로 묶어줘야 해!
    )

    # 태그까지 보여주려면 prefetch
    stops_qs = (
        RoutePlace.objects
        .filter(route=route)
        .select_related("place")
        .prefetch_related("place__tags")
        .order_by("stop_order")
    )

    stops = list(stops_qs)
    from_page = request.GET.get("from", "")

    return render(request, "routes/detail.html", {
        "route": route,
        "stops": stops,
        "from_page": from_page,    
    })

@login_required
@require_GET
def my_routes_json(request):
    """내 루트 목록을 (id, title)만 JSON으로 반환"""
    qs = Route.objects.filter(creator=request.user).order_by("-created_at")
    data = [{"id": r.id, "title": r.title} for r in qs]
    return JsonResponse({"routes": data})


@login_required
@require_POST
# apps/routes/views.py
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
    return redirect("routes:detail", route_id=route.id)

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
    return render(request, "routes/edit_route.html", {
        "route": route,
        "from_page": from_page,
        "stops": stops,
    })

@login_required
@require_POST
def update_route(request, route_id):
    route = get_object_or_404(Route, pk=route_id, creator=request.user)

    route.title = request.POST.get("title", "").strip()
    route.location_summary = request.POST.get("location_summary", "").strip()
    route.description = request.POST.get("description", "").strip()
    route.cover_photo_url = request.POST.get("cover_photo_url", "").strip()
    route.is_public = request.POST.get("is_public") == "true"
    route.save()

    return redirect(f"{reverse('routes:detail', args=[route.id])}?from={request.POST.get('from', '')}")

@login_required
@require_POST
def update_place_order(request, route_id):
    route = get_object_or_404(Route, pk=route_id, creator=request.user)

    try:
        import json
        data = json.loads(request.body)
        place_ids = data.get("place_ids", [])

        with transaction.atomic():
            # 1단계: 일단 겹치지 않는 큰 값으로 임시 설정
            for i, place_id in enumerate(place_ids):
                RoutePlace.objects.filter(route=route, place_id=place_id).update(stop_order=10000 + i)

            # 2단계: 진짜 순서로 다시 저장
            for i, place_id in enumerate(place_ids, start=1):
                RoutePlace.objects.filter(route=route, place_id=place_id).update(stop_order=i)

        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
