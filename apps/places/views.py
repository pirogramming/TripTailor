from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, BooleanField, Value, Count
from django.http import JsonResponse
from django.db.models import Q

import recommend 
from django.core.paginator import Paginator
from .models import Place, PlaceLike
import re


def parse_recommendations(recommendations):
    parsed = []
    i = 0
    pat = re.compile(r"\*\*(?:\[)?(.+?)(?:\])?\*\*")
    while i < len(recommendations):
        rec = recommendations[i]
        m = pat.search(rec)
        if m:
            place_name = m.group(1).strip()
            reason = ""
            if i + 1 < len(recommendations):
                nxt = recommendations[i + 1].strip()
                if nxt.startswith("- 이유:") or "이유:" in nxt:
                    reason = nxt.split("이유:", 1)[-1].strip()
                    parsed.append({"name": place_name, "reason": reason})
                    i += 2
                    continue
            parsed.append({"name": place_name, "reason": reason})
        i += 1
    return parsed

def with_like_meta(qs, user):
    """
    Place queryset에 like_count / is_liked 를 붙여준다.
    PlaceLike.place 의 related_name 은 'placelikes' 라는 전제.
    """
    qs = qs.annotate(like_count=Count('placelikes', distinct=True))
    if user.is_authenticated:
        qs = qs.annotate(
            is_liked=Exists(
                PlaceLike.objects.filter(place=OuterRef('pk'), user=user)
            )
        )
    else:
        qs = qs.annotate(
            is_liked=Value(False, output_field=BooleanField())
        )
    return qs

def find_places_by_names(names):
    # 간단 배치 매칭 (icontains OR)
    q = Q()
    for n in names:
        n = n.strip()
        if not n: 
            continue
        q |= Q(name__iexact=n) | Q(name__icontains=n) | Q(summary__icontains=n) | Q(address__icontains=n)
    if not q:
        return Place.objects.none()
    return Place.objects.filter(q).distinct()

def build_context_from_cached(prompt, followup, cached, user):
    recommended_places = []
    recommendations = cached.get('recommendations', []) or []
    question = cached.get('question', '') or ''
    show_followup = bool(question)

    parsed_recs = parse_recommendations(recommendations)
    names = [r["name"] for r in parsed_recs if r.get("name")]
    candidates_qs = with_like_meta(find_places_by_names(names), user)
    candidates = list(candidates_qs)  

    name_index = {p.name: p for p in candidates}
    lower_index = [(p.name.lower(), p) for p in candidates]

    for rec in parsed_recs:
        nm = rec["name"]
        place = name_index.get(nm)
        if not place:
            nm_l = nm.lower()
            place = next((p for name_l, p in lower_index if nm_l in name_l), None)
        if place and not any(x["place"].pk == place.pk for x in recommended_places):
            recommended_places.append({"place": place, "reason": rec.get("reason", "")})

    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places,
        'recommendations': recommendations,
        'question': question,
        'show_followup': show_followup,
    }

def get_recommendation_context(prompt, followup, user, page=1, page_size=20):
    """새로운 추천 엔진을 사용한 컨텍스트 생성"""
    if not prompt:
        return {
            'prompt': prompt,
            'followup': followup,
            'recommended_places': [],
            'recommendations': [],
            'question': '',
            'show_followup': False,
            'total_results': 0,
            'current_page': 1,
            'has_next': False,
            'total_pages': 0,
            'user_tags': [],
            'extracted_region': ''
        }

    user_input = f"{prompt} {followup}" if followup else prompt
    print(f"Processing recommendation for: '{user_input}'")
    
    try:
        # 새로운 추천 엔진 사용
        results = recommend.recommendation_engine.search_and_rerank(
            user_input, 
            page=page, 
            page_size=page_size
        )
        
        print(f"Recommendation results: {results.get('total', 0)} total, {len(results.get('results', []))} on page {page}")
        
        # 추천 결과를 Place 모델과 매칭
        recommended_places = []
        for result in results.get("results", []):
            # 이름으로 Place 찾기 (더 정확한 매칭)
            place = None
            
            # 1. 정확한 이름 매칭
            place = Place.objects.filter(name__iexact=result.name).first()
            
            # 2. 이름 포함 매칭
            if not place:
                place = Place.objects.filter(
                    Q(name__icontains=result.name) | 
                    Q(summary__icontains=result.name)
                ).first()
            
            # 3. 주소 포함 매칭
            if not place:
                place = Place.objects.filter(
                    address__icontains=result.name
                ).first()
            
            if place:
                # 좋아요 정보 추가
                place_with_meta = with_like_meta(Place.objects.filter(pk=place.pk), user).first()
                if place_with_meta:
                    recommended_places.append({
                        "place": place_with_meta,
                        "reason": result.reason or result.overview[:100],
                        "vector_score": result.vector_score,
                        "tag_score": result.tag_score,
                        "final_score": result.final_score
                    })
        
        print(f"Matched places: {len(recommended_places)} out of {len(results.get('results', []))}")
        
        return {
            'prompt': prompt,
            'followup': followup,
            'recommended_places': recommended_places,
            'recommendations': [],  # 기존 형식과 호환
            'question': '',  # 보충 질문 없음
            'show_followup': False,
            'total_results': results.get("total", 0),
            'current_page': results.get("page", 1),
            'has_next': results.get("has_next", False),
            'total_pages': results.get("total_pages", 0),
            'user_tags': results.get("user_tags", []),
            'extracted_region': results.get("extracted_region", "")
        }
        
    except Exception as e:
        print(f"Recommendation failed: {e}")
        # 기존 방식으로 폴백
        return get_recommendation_context_fallback(prompt, followup, user)

def get_recommendation_context_fallback(prompt, followup, user):
    """기존 추천 방식으로 폴백"""
    recommended_places, recommendations, question = [], [], ""
    show_followup = False

    if prompt:
        user_input = f"{prompt} {followup}" if followup else prompt
        try:
            result = recommend.app.invoke({"user_input": user_input}) or {}
        except Exception as e:
            result = {}

        # 키가 '보충_질문'일 수도 있고 'question'일 수도 있는 혼합 상황 방어
        question = (result.get("보충_질문")
                    or result.get("question")
                    or "")
        recommendations = result.get("recommendations") or []

        parsed_recs = parse_recommendations(recommendations)
        wanted_names = [r.get("name", "").strip() for r in parsed_recs if r.get("name")]
        if wanted_names:
            candidates = list(with_like_meta(find_places_by_names(wanted_names), user))
            by_name = {p.name: p for p in candidates}
            lower_index = [(p.name.lower(), p) for p in candidates]

            for rec in parsed_recs:
                key = (rec.get("name") or "").strip()
                if not key:
                    continue
                place = by_name.get(key)
                if not place:
                    key_l = key.lower()
                    place = next((p for name_l, p in lower_index if key_l in name_l), None)
                if place:
                    recommended_places.append({"place": place, "reason": rec.get("reason", "")})

        show_followup = bool(question)

    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places,
        'recommendations': recommendations,
        'question': question,
        'show_followup': show_followup,
        'total_results': len(recommended_places),
        'current_page': 1,
        'has_next': False,
        'total_pages': 1,
        'user_tags': [],
        'extracted_region': ''
    }

def main(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    class_filter = request.GET.get('place_class', '')

    qs = Place.objects.all().order_by('-id')
    if class_filter and class_filter.isdigit():
        qs = qs.filter(place_class=int(class_filter))

    # 헬퍼로 일괄 annotate
    qs = with_like_meta(qs, request.user)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    # 모델 호출 1회
    context = get_recommendation_context(prompt, followup, request.user)

    # 세션 저장
    request.session['last_reco'] = {
        'prompt': prompt,
        'followup': followup,
        'question': context.get('question', ''),
        'recommendations': context.get('recommendations', []),
    }

    context.update({
        'places': page_obj,
        'place_class': class_filter,
    })

    if context.get('recommended_places') and not context.get('show_followup'):
        from urllib.parse import urlencode
        q = {'prompt': prompt}
        if followup:
            q['followup'] = followup
        return redirect(f"/search/?{urlencode(q)}")

    return render(request, 'places/main.html', context)

def search(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    page = int(request.GET.get('page', 1))
    page_size = 20

    print(f"Search request - prompt: {prompt}, followup: {followup}, page: {page}")

    # 페이지네이션을 위한 추천 컨텍스트 생성
    context = get_recommendation_context(prompt, followup, request.user, page, page_size)
    
    print(f"Context - total_results: {context.get('total_results')}, current_page: {context.get('current_page')}, total_pages: {context.get('total_pages')}, has_next: {context.get('has_next')}")
    
    # 세션 업데이트
    request.session['last_reco'] = {
        'prompt': prompt,
        'followup': followup,
        'question': context.get('question', ''),
        'recommendations': context.get('recommendations', []),
    }

    return render(request, 'search.html', context)

def place_detail(request, pk):
    base = Place.objects.filter(pk=pk)
    if request.user.is_authenticated:
        base = base.annotate(
            is_liked=Exists(PlaceLike.objects.filter(user=request.user, place=OuterRef('pk'))),
            like_count=Count('placelikes', distinct=True),
        )
    else:
        base = base.annotate(
            is_liked=Value(False, output_field=BooleanField()),
            like_count=Count('placelikes', distinct=True),
        )
    place = get_object_or_404(base)
    return render(request, 'places/place_detail.html', {'place': place})

from django.views.decorators.http import require_POST
from django.db import IntegrityError, transaction

@login_required
@require_POST
def toggle_place_like(request, pk):
    place = get_object_or_404(Place, pk=pk)
    user = request.user

    # AJAX 판별 (Django 4+)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # 토글 (경쟁조건 안전)
    try:
        with transaction.atomic():
            obj, created = PlaceLike.objects.get_or_create(user=user, place=place)
            if created:
                liked = True
            else:
                obj.delete()
                liked = False
    except IntegrityError:
        # 극히 드문 경쟁 상황 방지용 리트라이
        liked = PlaceLike.objects.filter(user=user, place=place).exists()
        if liked:
            PlaceLike.objects.filter(user=user, place=place).delete()
            liked = False
        else:
            PlaceLike.objects.create(user=user, place=place)
            liked = True

    data = {
        'liked': liked,
        'like_count': PlaceLike.objects.filter(place=place).count(),
        'place_id': place.id,
    }

    if is_ajax:
        return JsonResponse(data)

    return redirect('places:place_detail', pk=place.id)