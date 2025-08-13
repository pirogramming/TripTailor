from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, BooleanField, Value, Count
from django.http import JsonResponse
from django.db.models import Q

import recommend 
from django.core.paginator import Paginator
from .models import Place, PlaceLike
from .services import VectorSearchService
import re

import csv
from pathlib import Path
from django.conf import settings
from django.utils.text import slugify

# 벡터 검색 서비스 인스턴스 (전역)
vector_search_service = VectorSearchService()


def _parse_selected_tags(request):
    raw = (request.GET.get('tags') or '').strip()
    selected = [t for t in raw.split(',') if t]
    match = (request.GET.get('match') or 'any').lower()  # 'any' or 'all'
    return selected, match, raw

# 1) 더 튼튼한 파서
def parse_recommendations(recommendations):
    parsed = []
    name_pat = re.compile(r"\*\*\s*\[?([^\]\*]+?)\]?\s*\*\*")  # **[이름]** 또는 **이름**
    numline_pat = re.compile(r"^\s*\d+\.\s*(.+?)\s*$")         # "1. 장소" 같은 라인 보강

    i = 0
    while i < len(recommendations):
        line = recommendations[i]
        name = None

        m = name_pat.search(line)
        if m:
            name = m.group(1).strip()
        else:
            # 굵게가 없을 때 숫자라인에서 이름 추출
            m2 = numline_pat.match(line)
            if m2:
                name = m2.group(1).strip()
                # 뒤에 ** **가 없는 케이스 보정: 괄호/양끝 기호 제거
                name = re.sub(r"^[\-\*\s\[]+|[\]\s]+$", "", name)

        reason = ""
        if name:
            if i + 1 < len(recommendations):
                nxt = recommendations[i + 1].strip()
                if nxt.startswith("- 이유:") or "이유:" in nxt:
                    reason = nxt.split("이유:", 1)[-1].strip()
                    parsed.append({"name": name, "reason": reason})
                    i += 2
                    continue
            parsed.append({"name": name, "reason": reason})
        i += 1
    return parsed


# 2) DB 매칭을 조금 더 느슨하게 (공백/괄호 제거 후 비교)
def find_places_by_names(names):
    from .models import Place
    def norm(s):
        import re
        s = s or ""
        s = re.sub(r"[\s\(\)\[\]「」『』\-_/·•~!@#$%^&*=+|:;\"'<>?,.]+", "", s)
        return s.lower()

    # 1차: 넓게 필터링 (QuerySet)
    q = Q()
    for raw in names:
        n = (raw or "").strip()
        if not n:
            continue
        q |= (Q(name__iexact=n) | Q(name__icontains=n) | Q(summary__icontains=n) | Q(address__icontains=n))
    if not q:
        return Place.objects.none()

    candidates = list(Place.objects.filter(q).distinct())

    # 2차: 정규화 유사 매칭으로 추림 → 최종 id 목록 만들기
    idx = {p.id: norm(p.name) for p in candidates}
    pick_ids = []
    for raw in names:
        key_n = norm(raw)
        hit = next((pid for pid, n2 in idx.items() if key_n == n2), None)
        if not hit:
            hit = next((pid for pid, n2 in idx.items() if key_n and key_n in n2), None)
        if hit and hit not in pick_ids:
            pick_ids.append(hit)

    # ✅ 항상 QuerySet 반환
    return Place.objects.filter(id__in=pick_ids)



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

def get_recommendation_context(prompt, followup, user):
    """벡터 검색 기반 추천 컨텍스트 생성"""
    recommended_places, recommendations, question = [], [], ""
    show_followup = False

    if not prompt:
        return {'prompt': prompt, 'followup': followup, 'recommended_places': [], 'recommendations': [], 'question': "", 'show_followup': False}

    user_input = f"{prompt} {followup}" if followup else prompt
    
    # 1. 벡터 검색으로 후보 장소들 가져오기
    try:
        vector_results = vector_search_service.search_places(
            query=user_input,
            limit=20,  # 충분한 후보 확보
            top_k=100
        )
        
        # 2. 기존 LLM 추천도 병행 (하이브리드 접근)
        try:
            llm_result = recommend.app.invoke({"user_input": user_input}) or {}
            question = (llm_result.get("보충_질문") or llm_result.get("question") or "")
            recommendations = llm_result.get("recommendations") or []
        except Exception:
            llm_result = {}
            question = ""
            recommendations = []
            
        # 3. 벡터 검색 결과를 우선으로 하되, LLM 추천과 병합
        used_place_ids = set()
        
        # 벡터 검색 결과를 추천 장소로 변환
        for result in vector_results[:10]:  # 상위 10개
            place = result['place']
            if place.id not in used_place_ids:
                # 좋아요 메타 추가
                place = with_like_meta(Place.objects.filter(id=place.id), user).first()
                if place:
                    reason = f"AI 추천 (유사도: {result['score']:.2f})"
                    recommended_places.append({"place": place, "reason": reason})
                    used_place_ids.add(place.id)
                    
        # 4. LLM 추천 결과도 추가 (중복 제거)
        if llm_result:
            parsed_recs = parse_recommendations(recommendations)
            names = [r.get("name","").strip() for r in parsed_recs if r.get("name")]
            
            # LLM이 추천한 장소들도 찾아서 추가
            llm_candidates = find_places_by_names(names)
            llm_annotated = list(with_like_meta(Place.objects.filter(id__in=[p.id for p in llm_candidates]), user))
            by_id = {p.id: p for p in llm_annotated}
            
            for nm in names:
                hit = next((p for p in llm_candidates if p.name == nm), None)
                hit = by_id.get(hit.id) if hit else None
                if hit and hit.id not in used_place_ids:
                    reason = next((r["reason"] for r in parsed_recs if r["name"] == nm and r.get("reason")), "LLM 추천")
                    recommended_places.append({"place": hit, "reason": reason})
                    used_place_ids.add(hit.id)
                    
        # 5. 결과가 부족하면 인기 장소로 보충
        if len(recommended_places) < 3:
            popular_places = with_like_meta(
                Place.objects.exclude(id__in=used_place_ids).order_by('-id')[:10], 
                user
            )
            for place in popular_places:
                recommended_places.append({"place": place, "reason": "인기 장소"})
                if len(recommended_places) >= 3:
                    break
                    
    except Exception as e:
        print(f"벡터 검색 실패, 기존 방식으로 Fallback: {e}")
        # Fallback: 기존 방식
        return get_recommendation_context_fallback(prompt, followup, user)

    show_followup = bool(question)
    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places[:3],  # 최종 3개 보장
        'recommendations': recommendations,
        'question': question,
        'show_followup': show_followup,
    }

def get_recommendation_context_fallback(prompt, followup, user):
    """기존 LLM 기반 추천 방식 (Fallback)"""
    recommended_places, recommendations, question = [], [], ""
    show_followup = False

    if not prompt:
        return {'prompt': prompt, 'followup': followup, 'recommended_places': [], 'recommendations': [], 'question': "", 'show_followup': False}

    user_input = f"{prompt} {followup}" if followup else prompt
    try:
        result = recommend.app.invoke({"user_input": user_input}) or {}
    except Exception:
        result = {}

    question = (result.get("보충_질문") or result.get("question") or "")
    recommendations = result.get("recommendations") or []

    # 1) 파싱으로 이름 가져오기
    parsed_recs = parse_recommendations(recommendations)
    names = [r.get("name","").strip() for r in parsed_recs if r.get("name")]

    # 2) 모델이 함께 돌려주는 '추천_장소명'도 합치기
    model_names = result.get("추천_장소명") or []
    for n in model_names:
        if n and n not in names:
            names.append(n)

    # 3) 이름 -> DB 매칭
    candidates = find_places_by_names(names)
    like_annotated = list(with_like_meta(Place.objects.filter(id__in=[p.id for p in candidates]), user))
    by_id = {p.id: p for p in like_annotated}

    # 추천 순서 보존해서 붙이기
    used = set()
    for nm in names:
        hit = next((p for p in candidates if p.name == nm), None)
        hit = by_id.get(hit.id) if hit else None
        if hit and hit.id not in used:
            reason = next((r["reason"] for r in parsed_recs if r["name"] == nm and r.get("reason")), "")
            recommended_places.append({"place": hit, "reason": reason})
            used.add(hit.id)

    # 4) 3개가 안되면 채우기: 남은 후보들(좋아요 많은 순)로 보충
    if len(recommended_places) < 3:
        remain = [p for p in like_annotated if p.id not in used]
        remain.sort(key=lambda x: getattr(x, "like_count", 0), reverse=True)
        for p in remain:
            recommended_places.append({"place": p, "reason": ""})
            used.add(p.id)
            if len(recommended_places) >= 3:
                break

    show_followup = bool(question)
    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places[:3],  # 최종 3개 보장
        'recommendations': recommendations,
        'question': question,
        'show_followup': show_followup,
    }

def get_more_recommendations_context(prompt, followup, user):
    """벡터 검색 기반 더 많은 추천 결과"""
    recommended_places, recommendations, question = [], [], ""
    
    if not prompt:
        return {'prompt': prompt, 'followup': followup, 'recommended_places': [], 'recommendations': [], 'question': "", 'show_followup': False}

    user_input = f"{prompt} {followup}" if followup else prompt
    
    try:
        # 벡터 검색으로 더 많은 결과 가져오기
        vector_results = vector_search_service.search_places(
            query=user_input,
            limit=100,  # 더 많은 결과
            top_k=200
        )
        
        # 좋아요 메타 추가
        used_place_ids = set()
        for result in vector_results:
            place = result['place']
            if place.id not in used_place_ids:
                # 좋아요 메타 추가
                place_with_meta = with_like_meta(Place.objects.filter(id=place.id), user).first()
                if place_with_meta:
                    reason = f"AI 추천 (유사도: {result['score']:.2f})"
                    recommended_places.append({"place": place_with_meta, "reason": reason})
                    used_place_ids.add(place.id)
                    
        # LLM 추천도 병행
        try:
            llm_result = recommend.app.invoke({"user_input": user_input}) or {}
            question = (llm_result.get("보충_질문") or llm_result.get("question") or "")
            recommendations = llm_result.get("recommendations") or []
            
            # LLM 추천 결과도 추가
            parsed_recs = parse_recommendations(recommendations)
            names = [r.get("name","").strip() for r in parsed_recs if r.get("name")]
            
            llm_candidates = find_places_by_names(names)
            llm_annotated = list(with_like_meta(Place.objects.filter(id__in=[p.id for p in llm_candidates]), user))
            by_id = {p.id: p for p in llm_annotated}
            
            for nm in names:
                hit = next((p for p in llm_candidates if p.name == nm), None)
                hit = by_id.get(hit.id) if hit else None
                if hit and hit.id not in used_place_ids:
                    reason = next((r["reason"] for r in parsed_recs if r["name"] == nm and r.get("reason")), "LLM 추천")
                    recommended_places.append({"place": hit, "reason": reason})
                    used_place_ids.add(hit.id)
                    
        except Exception:
            pass
            
    except Exception as e:
        print(f"벡터 검색 실패, 기존 방식으로 Fallback: {e}")
        # Fallback: 기존 방식
        return get_more_recommendations_context_fallback(prompt, followup, user)

    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places,
        'recommendations': recommendations,
        'question': question,
        'show_followup': False,
    }

def get_more_recommendations_context_fallback(prompt, followup, user):
    """기존 방식의 더 많은 추천 결과 (Fallback)"""
    recommended_places, recommendations, question = [], [], ""
    
    if not prompt:
        return {'prompt': prompt, 'followup': followup, 'recommended_places': [], 'recommendations': [], 'question': "", 'show_followup': False}

    user_input = f"{prompt} {followup}" if followup else prompt
    try:
        result = recommend.app.invoke({"user_input": user_input}) or {}
    except Exception:
        result = {}

    question = (result.get("보충_질문") or result.get("question") or "")
    recommendations = result.get("recommendations") or []

    # 1) 파싱으로 이름 가져오기
    parsed_recs = parse_recommendations(recommendations)
    names = [r.get("name","").strip() for r in parsed_recs if r.get("name")]

    # 2) 모델이 함께 돌려주는 '추천_장소명'도 합치기
    model_names = result.get("추천_장소명") or []
    for n in model_names:
        if n and n not in names:
            names.append(n)

    # 3) 이름 -> DB 매칭
    candidates = find_places_by_names(names)
    like_annotated = list(with_like_meta(Place.objects.filter(id__in=[p.id for p in candidates]), user))
    by_id = {p.id: p for p in like_annotated}

    # 추천 순서 보존해서 붙이기
    used = set()
    for nm in names:
        hit = next((p for p in candidates if p.name == nm), None)
        hit = by_id.get(hit.id) if hit else None
        if hit and hit.id not in used:
            reason = next((r["reason"] for r in parsed_recs if r["name"] == nm and r.get("reason")), "")
            recommended_places.append({"place": hit, "reason": reason})
            used.add(hit.id)

    # 4) 더 많은 결과를 위해 유사한 장소들도 추가
    if len(recommended_places) < 100:
        # 태그 기반으로 유사한 장소 찾기 (지역도 고려)
        if recommended_places:
            # 추천된 장소들의 태그들과 지역을 수집
            all_tags = set()
            all_regions = set()
            for rec in recommended_places:
                all_tags.update(rec['place'].tags.values_list('name', flat=True))
                all_regions.add(rec['place'].region)
            
            # 유사한 태그를 가진 장소들 찾기 (같은 지역 우선)
            similar_places = Place.objects.filter(tags__name__in=all_tags).exclude(
                id__in=[rec['place'].id for rec in recommended_places]
            ).distinct()
            
            # 좋아요 메타 추가
            similar_places = with_like_meta(similar_places, user)
            
            # 지역 우선순위로 정렬 (같은 지역이 먼저, 그 다음 좋아요 순)
            def sort_key(place):
                region_priority = 0 if place.region in all_regions else 1
                return (region_priority, -getattr(place, 'like_count', 0))
            
            sorted_places = sorted(similar_places, key=sort_key)
            
            # 추가
            for place in sorted_places[:100-len(recommended_places)]:
                reason = "유사한 장소"
                if place.region in all_regions:
                    reason = f"같은 지역({place.region})의 유사한 장소"
                recommended_places.append({"place": place, "reason": reason})
                if len(recommended_places) >= 100:
                    break

    return {
        'prompt': prompt,
        'followup': followup,
        'recommended_places': recommended_places,
        'recommendations': recommendations,
        'question': question,
        'show_followup': False,
    }




def main(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    class_filter = request.GET.get('place_class', '')

    # 기본 목록
    qs = Place.objects.all().order_by('-id')

    # 대분류 필터
    if class_filter and class_filter.isdigit():
        qs = qs.filter(place_class=int(class_filter))

    # ✅ 태그 필터 (Place.tags 기준)
    # URL 예: ?tags=레트로,야경&match=any
    selected, match_mode, raw_tags = _parse_selected_tags(request)
    if selected:
        # name/slug 둘 다 대응 (CSV 칩에서 name을 보내도, slug를 보내도 OK)
        cond = Q(tags__name__in=selected)
        if match_mode == 'all':
            # 모든 선택 태그를 다 가진 Place만
            qs = (qs.filter(cond)
                    .annotate(num_matched=Count('tags', filter=cond, distinct=True))
                    .filter(num_matched=len(selected)))
        else:
            # 하나라도 포함하면 통과
            qs = qs.filter(cond).distinct()

    # 좋아요 메타 붙이기
    qs = with_like_meta(qs, request.user)

    # 페이지네이션
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

    # 컨텍스트 합치기 (+ 태그 상태 전달)
    context.update({
        'places': page_obj,
        'place_class': class_filter,
        'tags': raw_tags,        # 예: "레트로,야경"
        'match': match_mode,     # 'any' or 'all'
        'selected_tags': selected,
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

    sess = request.session.get('last_reco')
    if sess and sess.get('prompt') == prompt and sess.get('followup') == followup:
        context = build_context_from_cached(prompt, followup, sess, request.user)
    else:
        context = get_recommendation_context(prompt, followup, request.user)

    return render(request, 'search.html', context)

def more_recommendations(request):
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    
    if not prompt:
        return redirect('places:search')
    
    # 더 많은 추천 결과 가져오기 (최대 100개)
    context = get_more_recommendations_context(prompt, followup, request.user)
    
    # 디버깅: 데이터 확인
    print(f"DEBUG: recommended_places count: {len(context.get('recommended_places', []))}")
    if context.get('recommended_places'):
        print(f"DEBUG: First place: {context['recommended_places'][0]}")
    
    # 페이지네이션 추가
    recommended_places = context['recommended_places']
    paginator = Paginator(recommended_places, 20)  # 페이지당 20개씩
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context['page_obj'] = page_obj
    context['recommended_places'] = page_obj.object_list
    
    print(f"DEBUG: Final context keys: {list(context.keys())}")
    print(f"DEBUG: Final recommended_places count: {len(context.get('recommended_places', []))}")
    
    return render(request, 'places/more_recommendations.html', context)

def more_recommendations_ajax(request):
    """AJAX 요청으로 더 많은 추천 결과를 반환하는 뷰"""
    from django.http import JsonResponse
    
    prompt = request.GET.get('prompt', '')
    followup = request.GET.get('followup', '')
    page = int(request.GET.get('page', 1))
    
    print(f"AJAX DEBUG: prompt='{prompt}', followup='{followup}', page={page}")
    
    if not prompt:
        print("AJAX DEBUG: No prompt provided")
        return JsonResponse({'error': '검색어가 필요합니다.'}, status=400)
    
    # 더 많은 추천 결과 가져오기
    context = get_more_recommendations_context(prompt, followup, request.user)
    recommended_places = context['recommended_places']
    
    print(f"AJAX DEBUG: Got {len(recommended_places)} recommended places")
    
    # 페이지네이션 - 한 번에 3개씩
    paginator = Paginator(recommended_places, 3)
    page_obj = paginator.get_page(page)
    
    print(f"AJAX DEBUG: Page {page} has {len(page_obj.object_list)} items")
    
    # JSON 응답용 데이터 준비
    places_data = []
    for rec in page_obj.object_list:
        place_data = {
            'place': {
                'id': rec['place'].id,
                'name': rec['place'].name,
                'region': rec['place'].region,
                'summary': rec['place'].summary,
                'tags': [{'name': tag.name} for tag in rec['place'].tags.all()],
                'is_liked': getattr(rec['place'], 'is_liked', False),
                'is_authenticated': request.user.is_authenticated
            },
            'reason': rec.get('reason', '')
        }
        places_data.append(place_data)
    
    response_data = {
        'places': places_data,
        'has_more': page_obj.has_next(),
        'current_page': page,
        'total_pages': paginator.num_pages,
        'total_count': paginator.count
    }
    
    print(f"AJAX DEBUG: Returning {len(places_data)} places, has_more={page_obj.has_next()}")
    
    return JsonResponse(response_data)

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

    return redirect('place_detail', pk=place.id)

def tags_json(request):
    csv_path = Path(settings.BASE_DIR) / "tags.csv"  # 방금 만든 CSV 경로
    items, seen = [], set()
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            name = row[0].strip().lstrip("#").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            items.append({"name": name, "slug": slugify(name, allow_unicode=True)})
    return JsonResponse(items, safe=False)

def vector_search_api(request):
    """벡터 검색 API 엔드포인트"""
    from django.http import JsonResponse
    
    query = request.GET.get('query', '')
    user_tags = request.GET.get('tags', '')
    region = request.GET.get('region', '')
    place_class = request.GET.get('place_class', '')
    limit = int(request.GET.get('limit', 10))
    
    if not query:
        return JsonResponse({'error': '검색어가 필요합니다.'}, status=400)
    
    try:
        # 태그 파싱
        tags_list = None
        if user_tags:
            tags_list = [tag.strip() for tag in user_tags.split(',') if tag.strip()]
            
        # place_class 파싱
        place_class_int = None
        if place_class and place_class.isdigit():
            place_class_int = int(place_class)
            
        # 벡터 검색 실행
        results = vector_search_service.search_places(
            query=query,
            user_tags=tags_list,
            region=region if region else None,
            place_class=place_class_int,
            limit=limit
        )
        
        # JSON 응답용 데이터 준비
        places_data = []
        for result in results:
            place_data = {
                'id': result['place'].id,
                'name': result['place'].name,
                'address': result['place'].address,
                'region': result['place'].region,
                'overview': result['place'].overview,
                'summary': result['place'].summary,
                'lat': result['lat'],
                'lng': result['lng'],
                'place_class': result['place_class'],
                'tags': result['tags'],
                'score': result['score'],
                'cosine_score': result['cosine_score'],
                'tag_score': result['tag_score'],
                'popularity_score': result['popularity_score']
            }
            places_data.append(place_data)
            
        response_data = {
            'query': query,
            'user_tags': tags_list,
            'region': region,
            'place_class': place_class_int,
            'results': places_data,
            'total_count': len(places_data)
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'error': f'검색 실패: {str(e)}'}, status=500)

def update_embeddings_api(request):
    """임베딩 업데이트 API 엔드포인트"""
    from django.http import JsonResponse
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST 요청만 허용됩니다.'}, status=405)
    
    place_ids = request.POST.get('place_ids', '')
    
    try:
        # place_ids 파싱
        ids_list = None
        if place_ids:
            ids_list = [int(pid.strip()) for pid in place_ids.split(',') if pid.strip().isdigit()]
            
        # 임베딩 업데이트 실행
        updated_count = vector_search_service.update_place_embeddings(ids_list)
        
        response_data = {
            'success': True,
            'updated_count': updated_count,
            'place_ids': ids_list
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'error': f'임베딩 업데이트 실패: {str(e)}'}, status=500)